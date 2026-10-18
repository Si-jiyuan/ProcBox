from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

from procbox.platforms.activity import ActivityMonitor, ActivitySnapshot
from procbox.ui.effects import Effect, EffectArt


class ActivityEffectDirector(QObject):
    """Maps process activity to the corresponding app sprite animations."""

    def __init__(
        self,
        sprites: dict,
        parent=None,
        interrupt: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._sprites = sprites
        self._interrupt = interrupt
        self._monitor = ActivityMonitor()
        self._previews: dict[str, tuple[Effect, float]] = {}
        self._last_warning: str | None = None

        EffectArt.warm()
        self._monitor.start()

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.update_effects)
        self._timer.start()

    def preview(self, app_id: str, effect: Effect, seconds: float = 8.0) -> None:
        self._previews[app_id] = (effect, time.monotonic() + seconds)
        self.update_effects()

    def clear_previews(self) -> None:
        self._previews.clear()
        self.update_effects()

    def update_effects(self) -> None:
        now = time.monotonic()
        for app_id, (_, expiry) in list(self._previews.items()):
            if expiry <= now:
                self._previews.pop(app_id, None)

        snapshot = self._monitor.snapshot()
        self._surface_warning(snapshot)
        audio_pids = snapshot.audio_output_pids
        audio_claimed = any(
            sprite.is_alive and set(sprite.app.pids) & audio_pids
            for sprite in self._sprites.values()
        )
        audio_fallback = set() if audio_claimed else audio_pids
        camera_pid = snapshot.camera_pid
        camera_claimed = camera_pid is not None and any(
            sprite.is_alive and camera_pid in sprite.app.pids for sprite in self._sprites.values()
        )
        camera_fallback = snapshot.camera_active and not camera_claimed
        for app_id, sprite in self._sprites.items():
            preview = self._previews.get(app_id)
            if preview is not None:
                if self._interrupt is not None:
                    self._interrupt(app_id)
                sprite.set_activity_effect(preview[0])
                continue
            desired = self._effect_for(
                sprite,
                snapshot,
                audio_fallback,
                camera_fallback,
            )
            if desired is not None and self._interrupt is not None:
                self._interrupt(app_id)
            sprite.set_activity_effect(desired)

    def stop(self) -> None:
        self._timer.stop()
        self._monitor.stop()

    def _surface_warning(self, snapshot: ActivitySnapshot) -> None:
        if not snapshot.warnings:
            return
        warning = snapshot.warnings[-1]
        if warning != self._last_warning:
            print(f"ProcBox activity: {warning}")
            self._last_warning = warning

    @staticmethod
    def _effect_for(
        sprite,
        snapshot: ActivitySnapshot,
        audio_fallback: set[int] | None = None,
        camera_fallback: bool = False,
    ) -> Effect | None:
        if not sprite.is_alive:
            return None
        pids = set(sprite.app.pids)
        if pids & snapshot.typing_pids:
            return Effect.TYPING
        if snapshot.camera_pid is not None and snapshot.camera_pid in pids:
            return Effect.CAMERA
        if (
            camera_fallback
            and snapshot.frontmost_pid is not None
            and snapshot.frontmost_pid in pids
        ):
            return Effect.CAMERA
        if pids & snapshot.audio_output_pids:
            return Effect.AUDIO
        if audio_fallback and snapshot.frontmost_pid is not None and snapshot.frontmost_pid in pids:
            return Effect.AUDIO
        if pids & snapshot.network_pids:
            return Effect.NETWORK
        return None
