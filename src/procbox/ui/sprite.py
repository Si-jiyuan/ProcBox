from __future__ import annotations

import random

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsObject

from procbox import config
from procbox.core.models import AppInfo
from procbox.core.motion import Motion, random_velocity, step


class AppSprite(QGraphicsObject):
    """One wandering app icon. Kept deliberately small and extensible."""

    activated = Signal(str)

    def __init__(self, app: AppInfo, parent=None) -> None:
        super().__init__(parent)
        self._app = app
        self._rng = random.Random()
        self._alive = True
        self._size = config.ICON_LOGICAL_SIZE
        self._icon_png = app.icon_png

        self._color_pixmap = self._build_pixmap(app)
        self._gray_pixmap: QPixmap | None = None

        vx, vy = random_velocity(self._rng)
        self._motion = Motion(0.0, 0.0, vx, vy)

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setTransformOriginPoint(self._size / 2.0, self._size / 2.0)
        self.setToolTip(self._tooltip())

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22.0)
        shadow.setOffset(0.0, 6.0)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        self._scale_anim = QPropertyAnimation(self, b"scale", self)
        self._fall_anim = QPropertyAnimation(self, b"rotation", self)
        self._fade_anim = QPropertyAnimation(self, b"opacity", self)

    @property
    def app(self) -> AppInfo:
        return self._app

    @property
    def is_alive(self) -> bool:
        return self._alive

    @property
    def icon_size(self) -> float:
        return self._size

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, self._size, self._size)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        pixmap = self._color_pixmap if self._alive else (self._gray_pixmap or self._color_pixmap)
        painter.drawPixmap(QPointF(0.0, 0.0), pixmap)

    def place(self, x: float, y: float) -> None:
        self._motion = Motion(x, y, self._motion.vx, self._motion.vy)
        self.setPos(x, y)
        self.setZValue(y + self._size)

    def advance(self, dt: float, width: float, height: float) -> None:
        if not self._alive:
            return
        self._motion = step(self._motion, dt, width, height, self._size, self._rng)
        self.setPos(self._motion.x, self._motion.y)
        self.setZValue(self._motion.y + self._size)

    def constrain(self, width: float, height: float) -> None:
        max_x = max(0.0, width - self._size)
        max_y = max(0.0, height - self._size)
        x = min(max(self._motion.x, 0.0), max_x)
        y = min(max(self._motion.y, 0.0), max_y)
        vx = self._motion.vx
        vy = self._motion.vy
        if x != self._motion.x:
            vx = -vx
        if y != self._motion.y:
            vy = -vy
        self._motion = Motion(x, y, vx, vy)
        self.setPos(x, y)
        self.setZValue(y + self._size)

    def update_app(self, app: AppInfo) -> None:
        self._app = app
        self.setToolTip(self._tooltip())
        if app.icon_png is not None and app.icon_png is not self._icon_png:
            self._icon_png = app.icon_png
            self._color_pixmap = self._build_pixmap(app)
            self._gray_pixmap = None
            self.update()
        if not self._alive:
            self.revive()

    def pop_in(self) -> None:
        self.setScale(0.2)
        self._scale_anim.stop()
        self._scale_anim.setDuration(360)
        self._scale_anim.setStartValue(0.2)
        self._scale_anim.setEndValue(1.0)
        self._scale_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._scale_anim.start()

    def die(self) -> None:
        if not self._alive:
            return
        self._alive = False
        self._gray_pixmap = self._to_grayscale(self._color_pixmap)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip(f"{self._app.name}\n已关闭")
        self.update()

        self._fall_anim.stop()
        target = self._rng.choice((-1.0, 1.0)) * self._rng.uniform(72.0, 96.0)
        self._fall_anim.setDuration(560)
        self._fall_anim.setStartValue(self.rotation())
        self._fall_anim.setEndValue(target)
        self._fall_anim.setEasingCurve(QEasingCurve.Type.OutBounce)
        self._fall_anim.start()

        self._fade_anim.stop()
        self._fade_anim.setDuration(420)
        self._fade_anim.setStartValue(self.opacity())
        self._fade_anim.setEndValue(0.5)
        self._fade_anim.start()

    def revive(self) -> None:
        if self._alive:
            return
        self._alive = True
        self._gray_pixmap = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._tooltip())
        self.update()

        vx, vy = random_velocity(self._rng)
        self._motion = Motion(self._motion.x, self._motion.y, vx, vy)
        self.setZValue(self._motion.y + self._size)

        self._fall_anim.stop()
        self._fall_anim.setDuration(420)
        self._fall_anim.setStartValue(self.rotation())
        self._fall_anim.setEndValue(0.0)
        self._fall_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._fall_anim.start()

        self._fade_anim.stop()
        self._fade_anim.setDuration(260)
        self._fade_anim.setStartValue(self.opacity())
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

        self.pop_in()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._alive:
            self.activated.emit(self._app.app_id)
        event.accept()

    def hoverEnterEvent(self, event) -> None:
        if self._alive:
            self._animate_scale(1.08, 130)
        event.accept()

    def hoverLeaveEvent(self, event) -> None:
        self._animate_scale(1.0, 160)
        event.accept()

    def _animate_scale(self, target: float, duration: int) -> None:
        self._scale_anim.stop()
        self._scale_anim.setDuration(duration)
        self._scale_anim.setStartValue(self.scale())
        self._scale_anim.setEndValue(target)
        self._scale_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scale_anim.start()

    def _tooltip(self) -> str:
        count = len(self._app.pids)
        return f"{self._app.name}\n{count} 个进程\n双击切换到该 App"

    def _build_pixmap(self, app: AppInfo) -> QPixmap:
        pixmap = QPixmap()
        if app.icon_png:
            pixmap.loadFromData(app.icon_png)
        if pixmap.isNull():
            return self._fallback_pixmap(app.name)

        scaled = pixmap.scaled(
            config.ICON_PIXELS,
            config.ICON_PIXELS,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QPixmap(config.ICON_PIXELS, config.ICON_PIXELS)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.drawPixmap(
            (config.ICON_PIXELS - scaled.width()) // 2,
            (config.ICON_PIXELS - scaled.height()) // 2,
            scaled,
        )
        painter.end()
        canvas.setDevicePixelRatio(2.0)
        return canvas

    @staticmethod
    def _fallback_pixmap(name: str) -> QPixmap:
        canvas = QPixmap(config.ICON_PIXELS, config.ICON_PIXELS)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        seed = sum(ord(char) for char in name) or 1
        color = QColor.fromHsv(seed * 47 % 360, 145, 190)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        margin = 8
        painter.drawRoundedRect(
            margin,
            margin,
            config.ICON_PIXELS - margin * 2,
            config.ICON_PIXELS - margin * 2,
            26,
            26,
        )

        font = QFont()
        font.setBold(True)
        font.setPixelSize(54)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        letter = name[:1].upper() if name else "?"
        painter.drawText(
            QRectF(0.0, 0.0, config.ICON_PIXELS, config.ICON_PIXELS),
            Qt.AlignmentFlag.AlignCenter,
            letter,
        )
        painter.end()
        canvas.setDevicePixelRatio(2.0)
        return canvas

    @staticmethod
    def _to_grayscale(source: QPixmap) -> QPixmap:
        image = source.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
        result = QPixmap.fromImage(image)
        result.setDevicePixelRatio(source.devicePixelRatio())
        return result
