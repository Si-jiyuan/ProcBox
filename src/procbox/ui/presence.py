from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer

from procbox.platforms.activity import ActivityMonitor, ActivitySnapshot
from procbox.ui.effects import Effect, EffectArt


class ActivityEffectDirector(QObject):
    """Maps process activity to the corresponding app sprite animations."""

    def __init__(self, sprites: dict, parent=None) -> None:
        super().__init__(parent)
        self._sprites = sprites
        self._monitor = ActivityMonitor()
        self._previews: dict[str, tuple[Effect, float]] = {}
        self._last_warning: str | None = None

        EffectArt.warm()
        self._monitor.start()

        self._timer = QTimer(self)
        self._timer.setInterval(500)
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
        for app_id, sprite in self._sprites.items():
            preview = self._previews.get(app_id)
            if preview is not None:
                sprite.set_activity_effect(preview[0])
                continue
            sprite.set_activity_effect(self._effect_for(sprite, snapshot))

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
    def _effect_for(sprite, snapshot: ActivitySnapshot) -> Effect | None:
        if not sprite.is_alive:
            return None
        pids = set(sprite.app.pids)
        if pids & snapshot.typing_pids:
            return Effect.TYPING
        if snapshot.camera_pid is not None and snapshot.camera_pid in pids:
            return Effect.CAMERA
        if pids & (snapshot.audio_input_pids | snapshot.audio_output_pids):
            return Effect.AUDIO
        if pids & snapshot.network_pids:
            return Effect.NETWORK
        return None
