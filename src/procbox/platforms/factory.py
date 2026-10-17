from __future__ import annotations

import sys

from procbox.platforms.base import PlatformAdapter, UnsupportedPlatformError


def create_platform_adapter() -> PlatformAdapter:
    if sys.platform == "darwin":
        from procbox.platforms.macos import MacOSAdapter

        return MacOSAdapter()
    if sys.platform == "win32":
        from procbox.platforms.windows import WindowsAdapter

        return WindowsAdapter()
    raise UnsupportedPlatformError(f"ProcBox does not support {sys.platform!r} yet.")
