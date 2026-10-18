from __future__ import annotations

import contextlib
import math
import random
import sys
import time

from PySide6.QtCore import (
    QElapsedTimer,
    QObject,
    QRectF,
    QRunnable,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QMainWindow

from procbox import config
from procbox.core.models import AppInfo
from procbox.core.relationships import RelationshipBook
from procbox.platforms.base import PlatformAdapter
from procbox.ui.care import CareDirector
from procbox.ui.chat import ChatDirector
from procbox.ui.fight import FightDirector
from procbox.ui.physics import ThrowPhysics
from procbox.ui.scene import PenScene, PenView
from procbox.ui.sprite import AppSprite


class _ScanSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _ScanWorker(QRunnable):
    def __init__(self, adapter: PlatformAdapter) -> None:
        super().__init__()
        self._adapter = adapter
        self.signals = _ScanSignals()

    @Slot()
    def run(self) -> None:
        try:
            apps = self._adapter.scan_apps()
        except Exception as exc:  # noqa: BLE001 - surface any platform failure
            with contextlib.suppress(RuntimeError):
                self.signals.failed.emit(str(exc))
        else:
            with contextlib.suppress(RuntimeError):
                self.signals.finished.emit(apps)


class MainWindow(QMainWindow):
    def __init__(self, adapter: PlatformAdapter) -> None:
        super().__init__()
        self._adapter = adapter
        self._sprites: dict[str, AppSprite] = {}
        self._rng = random.Random()
        self._scanning = False
        self._pending_scan = False
        self._active_worker: _ScanWorker | None = None
        self._last_error: str | None = None
        self._first_scan_done = False
        self._last_occlusion_check = 0.0
        self._window_occluded = False
        self._occlusion_supported = (
            sys.platform == "darwin" and QGuiApplication.platformName() == "cocoa"
        )

        self.setWindowTitle("ProcBox")
        self.resize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        self.setMinimumSize(config.MIN_WINDOW_WIDTH, config.MIN_WINDOW_HEIGHT)
        self._apply_palette()

        self._scene = PenScene(self)
        self._scene.setItemIndexMethod(PenScene.ItemIndexMethod.NoIndex)
        self._scene.setSceneRect(
            QRectF(0.0, 0.0, float(config.WINDOW_WIDTH), float(config.WINDOW_HEIGHT))
        )

        self._view = PenView(self._scene, self)
        self._view.viewport_resized.connect(self._on_view_resized)
        self.setCentralWidget(self._view)

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

        self._relationships = RelationshipBook()
        self._chat = ChatDirector(
            self._scene,
            self._sprites,
            self._rng,
            self,
            relationships=self._relationships,
        )
        self._fight = FightDirector(
            self._scene,
            self._sprites,
            self._rng,
            self,
            relationships=self._relationships,
        )
        self._care = CareDirector(
            self._scene,
            self._sprites,
            self._relationships,
            self,
        )
        self._physics = ThrowPhysics(self._sprites, self._rng)

        self._clock = QElapsedTimer()
        self._clock.start()

        self._move_timer = QTimer(self)
        self._move_timer.setInterval(config.TICK_INTERVAL_MS)
        self._move_timer.timeout.connect(self._tick)
        self._move_timer.start()

        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(config.REFRESH_INTERVAL_MS)
        self._scan_timer.timeout.connect(self._request_scan)
        self._scan_timer.start()

        QTimer.singleShot(0, self._request_scan)

    def _apply_palette(self) -> None:
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#111419"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#111419"))
        self.setPalette(palette)

    @Slot()
    def _request_scan(self) -> None:
        if self._scanning:
            self._pending_scan = True
            return
        self._scanning = True
        worker = _ScanWorker(self._adapter)
        worker.signals.finished.connect(self._on_scan_finished)
        worker.signals.failed.connect(self._on_scan_failed)
        self._active_worker = worker
        self._pool.start(worker)

    @Slot(object)
    def _on_scan_finished(self, apps: list[AppInfo]) -> None:
        self._finish_scan()
        self._apply_apps(apps)
        self.setWindowTitle(f"ProcBox · {len(apps)} 个应用")
        self._last_error = None
        if not self._first_scan_done:
            self._first_scan_done = True
            QTimer.singleShot(1_000, self._request_scan)

    @Slot(str)
    def _on_scan_failed(self, message: str) -> None:
        self._finish_scan()
        if message != self._last_error:
            print(f"ProcBox scan failed: {message}", file=sys.stderr)
            self._last_error = message
        self.setWindowTitle("ProcBox · 扫描失败")

    def _finish_scan(self) -> None:
        self._scanning = False
        self._active_worker = None
        if self._pending_scan:
            self._pending_scan = False
            self._request_scan()

    def _apply_apps(self, apps: list[AppInfo]) -> None:
        seen: set[str] = set()
        for app in apps:
            seen.add(app.app_id)
            sprite = self._sprites.get(app.app_id)
            if sprite is None:
                sprite = self._create_sprite(app)
            else:
                sprite.update_app(app)

        for app_id, sprite in self._sprites.items():
            if app_id not in seen:
                sprite.die()

    def _create_sprite(self, app: AppInfo) -> AppSprite:
        sprite = AppSprite(app)
        sprite.activated.connect(self._activate_app)
        sprite.drag_started.connect(self._on_drag_started)
        self._scene.addItem(sprite)
        x, y = self._spawn_position(sprite.size)
        sprite.place(x, y)
        sprite.pop_in()
        self._sprites[app.app_id] = sprite
        return sprite

    def _spawn_position(self, sprite_size: float) -> tuple[float, float]:
        rect = self._scene.sceneRect()
        max_x = max(0.0, rect.width() - sprite_size)
        max_y = max(0.0, rect.height() - sprite_size)
        best = (self._rng.uniform(0.0, max_x), self._rng.uniform(0.0, max_y))

        for _ in range(18):
            candidate = (self._rng.uniform(0.0, max_x), self._rng.uniform(0.0, max_y))
            clear = True
            for sprite in self._sprites.values():
                if not sprite.is_alive:
                    continue
                distance = math.hypot(
                    candidate[0] - sprite.x(),
                    candidate[1] - sprite.y(),
                )
                if distance < sprite_size * 1.25:
                    clear = False
                    break
            best = candidate
            if clear:
                break
        return best

    @Slot(str)
    def _activate_app(self, app_id: str) -> None:
        sprite = self._sprites.get(app_id)
        if sprite is not None and sprite.is_alive:
            self._adapter.activate(sprite.app)

    @Slot(str)
    def _on_drag_started(self, app_id: str) -> None:
        sprite = self._sprites.get(app_id)
        if sprite is None:
            return
        self._chat.interrupt_for(sprite)
        self._fight.interrupt_for(sprite)
        self._care.interrupt_for(sprite)

    @Slot(QRectF)
    def _on_view_resized(self, rect: QRectF) -> None:
        width = max(0.0, rect.width())
        height = max(0.0, rect.height())
        for sprite in self._sprites.values():
            sprite.constrain(width, height)

    def _tick(self) -> None:
        if self.isMinimized():
            return

        now = time.monotonic()
        if self._occlusion_supported and now - self._last_occlusion_check >= 0.25:
            self._last_occlusion_check = now
            self._window_occluded = self._adapter.is_window_occluded(int(self.winId()))

        handle = self.windowHandle()
        if not self._window_occluded and handle is not None and not handle.isExposed():
            return

        desired_interval = (
            config.TICK_INTERVAL_OCCLUDED_MS if self._window_occluded else config.TICK_INTERVAL_MS
        )
        if self._move_timer.interval() != desired_interval:
            self._move_timer.setInterval(desired_interval)
        dt = min(self._clock.restart() / 1000.0, 0.05)
        width = self._scene.sceneRect().width()
        height = self._scene.sceneRect().height()
        avoid_zone = self._fight.avoid_zone
        for sprite in self._sprites.values():
            sprite.advance(dt, width, height, avoid_zone)
        self._physics.step(dt, width, height)

    def closeEvent(self, event) -> None:
        self._move_timer.stop()
        self._scan_timer.stop()
        self._chat.stop()
        self._fight.stop()
        self._care.stop()
        self._pool.clear()
        self._adapter.shutdown()
        super().closeEvent(event)
