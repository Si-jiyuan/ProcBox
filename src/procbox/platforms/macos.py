from __future__ import annotations

import subprocess
import tempfile
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


class MacOSAdapter(PlatformAdapter):
    def __init__(self) -> None:
        self._icon_cache: dict[str, bytes | None] = {}

    @property
    def platform_name(self) -> str:
        return "macos"

    def scan_apps(self) -> list[AppInfo]:
        groups: dict[str, _AppGroup] = {}

        for proc in psutil.process_iter(["pid", "name", "username", "exe"]):
            try:
                bundle_path = _is_user_application(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            if bundle_path is None:
                continue

            group = groups.setdefault(
                bundle_path,
                _AppGroup(exe_path=proc.info.get("exe") or ""),
            )
            group.pids.append(proc.info["pid"])

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
                )
            )

        apps.sort(key=lambda item: item.name.casefold())
        return apps

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
            return self._icon_cache[bundle_path]

        data = self._icon_from_workspace(bundle_path) or self._icon_from_icns(bundle_path)
        self._icon_cache[bundle_path] = data
        return data

    @staticmethod
    def _icon_from_workspace(bundle_path: str) -> bytes | None:
        """Ask LaunchServices for the same icon Finder shows."""
        try:
            from AppKit import (
                NSBitmapImageRep,
                NSCalibratedRGBColorSpace,
                NSGraphicsContext,
                NSMakeRect,
                NSWorkspace,
            )
        except ImportError:
            return None

        try:
            image = NSWorkspace.sharedWorkspace().iconForFile_(bundle_path)
            if image is None:
                return None

            size = ICON_SIZE
            rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(  # noqa: E501
                None,
                size,
                size,
                8,
                4,
                True,
                False,
                NSCalibratedRGBColorSpace,
                0,
                0,
            )
            if rep is None:
                return None

            context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
            if context is None:
                return None
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.setCurrentContext_(context)
            image.drawInRect_(NSMakeRect(0, 0, size, size))
            NSGraphicsContext.restoreGraphicsState()

            # NSBitmapImageFileTypePNG == 4
            data = rep.representationUsingType_properties_(4, {})
            return bytes(data) if data else None
        except Exception:
            return None

    @staticmethod
    def _icon_from_icns(bundle_path: str) -> bytes | None:
        """Fallback for environments without PyObjC."""
        resources = Path(bundle_path) / "Contents" / "Resources"
        if not resources.is_dir():
            return None

        icns_files = sorted(resources.glob("*.icns"))
        if not icns_files:
            return None
        preferred = resources / "AppIcon.icns"
        icns_path = preferred if preferred.exists() else icns_files[0]

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
