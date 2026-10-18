from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ActivitySnapshot:
    typing_pids: set[int] = field(default_factory=set)
    network_pids: set[int] = field(default_factory=set)
    audio_input_pids: set[int] = field(default_factory=set)
    audio_output_pids: set[int] = field(default_factory=set)
    camera_pid: int | None = None
    frontmost_pid: int | None = None
    warnings: list[str] = field(default_factory=list)


class ActivityMonitor:
    """Collects keyboard/audio/camera state from a native helper and nettop."""

    NETWORK_THRESHOLD = 4_096.0

    def __init__(self, helper_path: Path | None = None) -> None:
        self._helper_path = helper_path or (Path(__file__).with_name("bin") / "procbox-activity")
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._typing: dict[int, float] = {}
        self._network: dict[int, float] = {}
        self._audio_in: set[int] = set()
        self._audio_out: set[int] = set()
        self._audio_seen = 0.0
        self._camera = False
        self._camera_pid: int | None = None
        self._frontmost: int | None = None
        self._warnings: list[str] = []
        self._helper: subprocess.Popen[str] | None = None
        self._threads: list[threading.Thread] = []
        self._previous_net: dict[int, tuple[int, int]] = {}

    @property
    def helper_available(self) -> bool:
        return self._helper_path.is_file()

    def start(self) -> None:
        self._stop.clear()
        if self._helper_path.is_file():
            self._threads.append(
                threading.Thread(target=self._read_helper, name="procbox-activity", daemon=True)
            )
        else:
            self._add_warning("activity helper missing; build helpers/activity_helper.swift")
        self._threads.append(
            threading.Thread(target=self._read_network, name="procbox-network", daemon=True)
        )
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        helper = self._helper
        if helper is not None and helper.poll() is None:
            helper.terminate()
            try:
                helper.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                helper.kill()
        for thread in self._threads:
            thread.join(timeout=1.0)

    def snapshot(self) -> ActivitySnapshot:
        now = time.monotonic()
        with self._lock:
            typing = {pid for pid, expiry in self._typing.items() if expiry > now}
            network = {pid for pid, expiry in self._network.items() if expiry > now}
            audio_in = set(self._audio_in) if now - self._audio_seen <= 3.0 else set()
            audio_out = set(self._audio_out) if now - self._audio_seen <= 3.0 else set()
            return ActivitySnapshot(
                typing_pids=typing,
                network_pids=network,
                audio_input_pids=audio_in,
                audio_output_pids=audio_out,
                camera_pid=self._camera_pid,
                frontmost_pid=self._frontmost,
                warnings=list(self._warnings),
            )

    def _add_warning(self, message: str) -> None:
        with self._lock:
            if message not in self._warnings:
                self._warnings.append(message)

    def _read_helper(self) -> None:
        if self._stop.is_set():
            return
        try:
            self._helper = subprocess.Popen(
                [str(self._helper_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self._add_warning(f"activity helper failed: {exc}")
            return

        if self._stop.is_set():
            self._helper.terminate()
            return

        assert self._helper.stdout is not None
        for line in self._helper.stdout:
            if self._stop.is_set():
                break
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._consume_helper_payload(payload)

    def _consume_helper_payload(self, payload: dict) -> None:
        now = time.monotonic()
        with self._lock:
            if "error" in payload:
                self._warnings.append(str(payload["error"]))
                return
            if "typing" in payload:
                with contextlib.suppress(TypeError, ValueError):
                    self._typing[int(payload["typing"])] = now + 1.5
                return

            frontmost = payload.get("frontmost")
            if isinstance(frontmost, int) and frontmost > 0:
                self._frontmost = frontmost
            audio_in = payload.get("audio_in", [])
            audio_out = payload.get("audio_out", [])
            if isinstance(audio_in, list):
                self._audio_in = {int(pid) for pid in audio_in if str(pid).isdigit()}
                self._audio_seen = now
            if isinstance(audio_out, list):
                self._audio_out = {int(pid) for pid in audio_out if str(pid).isdigit()}
                self._audio_seen = now

            camera = bool(payload.get("camera"))
            if camera and not self._camera:
                self._camera_pid = self._frontmost
            if not camera:
                self._camera_pid = None
            self._camera = camera

    def _read_network(self) -> None:
        nettop = shutil.which("nettop")
        if nettop is None:
            self._add_warning("nettop not found; network detection disabled")
            return

        while not self._stop.wait(2.0):
            try:
                result = subprocess.run(
                    [
                        nettop,
                        "-P",
                        "-L",
                        "1",
                        "-x",
                        "-J",
                        "bytes_in,bytes_out",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=6,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            self._consume_nettop(result.stdout)

    def _consume_nettop(self, output: str) -> None:
        now = time.monotonic()
        samples: dict[int, tuple[int, int]] = {}
        for line in output.splitlines()[1:]:
            parts = line.split(",")
            if len(parts) < 3 or not parts[0]:
                continue
            process, _, pid_text = parts[0].rpartition(".")
            if not process or not pid_text.isdigit():
                continue
            try:
                pid = int(pid_text)
                bytes_in = int(parts[1] or 0)
                bytes_out = int(parts[2] or 0)
            except ValueError:
                continue
            samples[pid] = (bytes_in, bytes_out)

        with self._lock:
            for pid, (bytes_in, bytes_out) in samples.items():
                previous = self._previous_net.get(pid)
                if previous is not None:
                    delta = max(0, bytes_in - previous[0]) + max(0, bytes_out - previous[1])
                    if delta / 2.0 >= self.NETWORK_THRESHOLD:
                        self._network[pid] = now + 3.0
            self._previous_net = samples
