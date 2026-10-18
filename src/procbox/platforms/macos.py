from __future__ import annotations

import contextlib
import plistlib
import subprocess
import sys
import tempfile
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from procbox.core.models import AppInfo
from procbox.platforms.base import PlatformAdapter

MAC_DAEMON_BLACKLIST = {
    "networkserviceproxy",
    "proactiveeventtrackerd",
    "adprivacyd",
    "PasswordBreachAgent",
    "com.apple.WebKit.Networking",
    "com.apple.WebKit.WebContent",
    "kernel_task",
    "launchd",
}
SYSTEM_PREFIXES = ("/System/Library/", "/usr/sbin/", "/sbin/", "/usr/bin/")
ICON_SIZE = 256
ICON_CACHE_LIMIT = 128


def app_bundle_from_executable(exe_path: str) -> str | None:
    """Return ``/Applications/Foo.app`` for an executable inside a bundle."""
    marker = ".app/"
    index = exe_path.find(marker)
    if index == -1:
        return None
    return exe_path[: index + len(".app")]


def _is_user_application(proc: psutil.Process) -> str | None:
    app = proc.info
    name = (app.get("name") or "").strip()
    exe_path = app.get("exe") or ""

    if not exe_path or name in MAC_DAEMON_BLACKLIST:
        return None
    if app.get("username") == "root":
        return None
    if exe_path.startswith(SYSTEM_PREFIXES):
        return None

    bundle_path = app_bundle_from_executable(exe_path)
    if bundle_path is None:
        # Not a GUI bundle. Daemons all live here, so ignore them.
        return None
    return bundle_path


@dataclass
class _AppGroup:
    pids: list[int] = field(default_factory=list)
    exe_path: str = ""
    memory_bytes: int = 0
    cpu_percent: float = 0.0


class _ObjCWindowProbe:
    """Ask NSWindow for its occlusion state without importing AppKit."""

    def __init__(self) -> None:
        import ctypes

        self._ctypes = ctypes
        self._lib = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        self._lib.object_getClassName.restype = ctypes.c_char_p
        self._lib.object_getClassName.argtypes = [ctypes.c_void_p]
        self._lib.sel_registerName.restype = ctypes.c_void_p
        self._lib.sel_registerName.argtypes = [ctypes.c_char_p]
        self._lib.objc_msgSend.restype = ctypes.c_void_p
        self._lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._window_selector = self._lib.sel_registerName(b"window")
        self._occlusion_selector = self._lib.sel_registerName(b"occlusionState")

    def is_occluded(self, window_id: int) -> bool:
        if not window_id:
            return False
        ctypes = self._ctypes
        pointer = ctypes.c_void_p(int(window_id))
        class_name = self._lib.object_getClassName(pointer)
        if not class_name:
            return False

        message = self._lib.objc_msgSend
        if b"NSView" in class_name:
            message.restype = ctypes.c_void_p
            message.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            window = message(pointer, self._window_selector)
        else:
            window = int(window_id)
        if not window:
            return False

        # NSWindowOcclusionStateVisible == 1 << 1
        message.restype = ctypes.c_ulong
        message.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        state = message(ctypes.c_void_p(window), self._occlusion_selector)
        return not bool(state & (1 << 1))


class MacOSAdapter(PlatformAdapter):
    def __init__(self) -> None:
        self._icon_cache: OrderedDict[str, bytes | None] = OrderedDict()
        self._cpu_samples: dict[int, tuple[float, float]] = {}
        self._window_probe: _ObjCWindowProbe | None = None
        self._window_probe_failed = False

    @property
    def platform_name(self) -> str:
        return "macos"

    def scan_apps(self) -> list[AppInfo]:
        groups: dict[str, _AppGroup] = {}
        now = time.monotonic()
        cpu_samples: dict[int, tuple[float, float]] = {}

        for proc in psutil.process_iter(["pid", "name", "username", "exe"]):
            try:
                bundle_path = _is_user_application(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            if bundle_path is None:
                continue

            pid = proc.info["pid"]
            group = groups.setdefault(
                bundle_path,
                _AppGroup(exe_path=proc.info.get("exe") or ""),
            )
            group.pids.append(pid)

            with contextlib.suppress(
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess,
            ):
                group.memory_bytes += proc.memory_info().rss

            with contextlib.suppress(
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess,
            ):
                times = proc.cpu_times()
                cpu_total = times.user + times.system
                previous = self._cpu_samples.get(pid)
                if previous is not None:
                    elapsed = now - previous[1]
                    if elapsed > 0.0:
                        group.cpu_percent += max(
                            0.0,
                            (cpu_total - previous[0]) / elapsed * 100.0,
                        )
                cpu_samples[pid] = (cpu_total, now)

        self._cpu_samples = cpu_samples

        apps: list[AppInfo] = []
        for bundle_path, group in groups.items():
            apps.append(
                AppInfo(
                    app_id=bundle_path,
                    name=Path(bundle_path).stem,
                    pids=tuple(sorted(group.pids)),
                    bundle_path=bundle_path,
                    exe_path=group.exe_path,
                    icon_png=self._load_icon(bundle_path),
                    memory_bytes=group.memory_bytes,
                    cpu_percent=group.cpu_percent,
                )
            )

        apps.sort(key=lambda item: item.name.casefold())
        return apps

    def is_window_occluded(self, window_id: int) -> bool:
        if self._window_probe_failed:
            return False
        if self._window_probe is None:
            try:
                self._window_probe = _ObjCWindowProbe()
            except Exception:
                self._window_probe_failed = True
                return False
        try:
            return self._window_probe.is_occluded(window_id)
        except Exception:
            self._window_probe_failed = True
            return False

    def activate(self, app: AppInfo) -> bool:
        target = app.bundle_path or app.exe_path
        if not target:
            return False
        try:
            subprocess.Popen(
                ["open", target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return False
        return True

    def _load_icon(self, bundle_path: str) -> bytes | None:
        if bundle_path in self._icon_cache:
            self._icon_cache.move_to_end(bundle_path)
            return self._icon_cache[bundle_path]

        data = self._icon_from_icns(bundle_path)
        if data is None:
            data = self._icon_from_appkit(bundle_path)
        self._icon_cache[bundle_path] = data
        self._icon_cache.move_to_end(bundle_path)
        while len(self._icon_cache) > ICON_CACHE_LIMIT:
            self._icon_cache.popitem(last=False)
        return data

    @staticmethod
    def _preferred_icns_path(resources: Path, bundle_path: str) -> Path | None:
        icon_names: list[str] = []
        info_path = Path(bundle_path) / "Contents" / "Info.plist"
        with contextlib.suppress(OSError, plistlib.InvalidFileException, ValueError):
            with info_path.open("rb") as handle:
                info = plistlib.load(handle)
            for key in ("CFBundleIconFile", "CFBundleIconName"):
                name = info.get(key)
                if isinstance(name, str) and name:
                    icon_names.append(name)

        for name in icon_names:
            candidates = [name]
            if not name.lower().endswith(".icns"):
                candidates.append(name + ".icns")
            for candidate in candidates:
                direct = resources / candidate
                if direct.is_file():
                    return direct
                matches = sorted(resources.rglob(Path(candidate).name))
                if matches:
                    return matches[0]

        preferred = resources / "AppIcon.icns"
        if preferred.is_file():
            return preferred

        icns_files = sorted(resources.rglob("*.icns"))
        if not icns_files:
            return None

        app_stem = Path(bundle_path).stem.casefold()
        for path in icns_files:
            if app_stem in path.name.casefold():
                return path
        non_file_icons = [path for path in icns_files if ".ico.icns" not in path.name.casefold()]
        return (non_file_icons or icns_files)[0]

    @staticmethod
    def _icon_from_appkit(bundle_path: str) -> bytes | None:
        """Use a short-lived helper process so AppKit never stays in ProcBox."""
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "procbox.platforms._icon_helper",
                    bundle_path,
                ],
                check=False,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0 or not result.stdout.startswith(b"\x89PNG"):
            return None
        return result.stdout

    @classmethod
    def _icon_from_icns(cls, bundle_path: str) -> bytes | None:
        """Extract the app icon from its .icns file without loading AppKit."""
        resources = Path(bundle_path) / "Contents" / "Resources"
        if not resources.is_dir():
            return None

        icns_path = cls._preferred_icns_path(resources, bundle_path)
        if icns_path is None:
            return None

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "icon.png"
                subprocess.run(
                    [
                        "sips",
                        "-s",
                        "format",
                        "png",
                        "-Z",
                        str(ICON_SIZE),
                        str(icns_path),
                        "--out",
                        str(output),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
                return output.read_bytes()
        except (OSError, subprocess.SubprocessError):
            return None
