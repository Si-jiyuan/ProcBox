from __future__ import annotations

from procbox.core.models import AppInfo
from procbox.platforms.base import PlatformAdapter, UnsupportedPlatformError

_MESSAGE = "Windows support is planned but not implemented yet."


class WindowsAdapter(PlatformAdapter):
    """Placeholder for the future Windows strategy.

    When this gets implemented it should discover top-level GUI processes,
    extract their icons from executables, and foreground the matching window.
    The rest of ProcBox only depends on the PlatformAdapter contract.
    """

    @property
    def platform_name(self) -> str:
        return "windows"

    def scan_apps(self) -> list[AppInfo]:
        raise UnsupportedPlatformError(_MESSAGE)

    def activate(self, app: AppInfo) -> bool:
        raise UnsupportedPlatformError(_MESSAGE)
