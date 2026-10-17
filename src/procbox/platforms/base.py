from __future__ import annotations

from abc import ABC, abstractmethod

from procbox.core.models import AppInfo


class PlatformError(RuntimeError):
    """Base class for platform adapter failures."""


class UnsupportedPlatformError(PlatformError):
    """Raised when ProcBox is started on a platform without an adapter."""


class PlatformAdapter(ABC):
    """Contract shared by every platform implementation.

    Everything that touches OS-specific APIs stays behind this interface so the
    UI and motion engine remain platform agnostic.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str: ...

    @abstractmethod
    def scan_apps(self) -> list[AppInfo]:
        """Return the user-facing applications that are currently running."""

    @abstractmethod
    def activate(self, app: AppInfo) -> bool:
        """Bring a running application to the foreground."""

    def shutdown(self) -> None:  # noqa: B027 - optional hook, not every platform needs it
        """Release platform resources, if any."""
