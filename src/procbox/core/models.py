from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class AppInfo:
    """A user-facing application discovered by a platform strategy."""

    app_id: str
    name: str
    pids: tuple[int, ...] = ()
    bundle_path: str | None = None
    exe_path: str | None = None
    icon_png: bytes | None = None

    def with_pids(self, pids: tuple[int, ...]) -> AppInfo:
        return replace(self, pids=pids)
