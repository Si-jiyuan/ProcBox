from __future__ import annotations

import math
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

from procbox import config

LOGICAL_SIZE = config.SPRITE_LOGICAL_SIZE
PIXELS = int(LOGICAL_SIZE * 2)
FRAME_COUNT = 8
FRAME_FPS = 10.0

INK = QColor("#111111")
OUTLINE = QColor("#FFFFFF")
WOOD = QColor("#9A6844")
DESK = QColor("#7A5035")
SCREEN = QColor("#22313D")
SCREEN_LIGHT = QColor("#5BC0EB")
PHONE = QColor("#202A36")
CAMERA = QColor("#2B3038")
LENS = QColor("#5BC0EB")
MEGAPHONE = QColor("#E85D4A")
ACCENT = QColor("#FFD166")


class Effect(Enum):
    TYPING = "typing"
    NETWORK = "network"
    CAMERA = "camera"
    AUDIO = "audio"


def _stroke(painter: QPainter, path: QPainterPath, color: QColor, width: float) -> None:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


def _arm(painter: QPainter, start: QPointF, control: QPointF, end: QPointF) -> None:
    path = QPainterPath(start)
    path.quadTo(control, end)
    _stroke(painter, path, OUTLINE, 6.4)
    _stroke(painter, path, INK, 4.0)
    painter.setPen(QPen(OUTLINE, 1.4))
    painter.setBrush(INK)
    painter.drawEllipse(end, 3.5, 3.5)


def _hand(painter: QPainter, center: QPointF) -> None:
    painter.setPen(QPen(OUTLINE, 1.5))
    painter.setBrush(INK)
    painter.drawEllipse(center, 3.6, 3.6)


class EffectArt:
    """Renders each effect frame once; the app only blits QPixmaps afterwards."""

    _cache: dict[Effect, list[QPixmap]] = {}

    @classmethod
    def warm(cls) -> None:
        for effect in Effect:
            cls.frames(effect)

    @classmethod
    def frames(cls, effect: Effect) -> list[QPixmap]:
        if effect not in cls._cache:
            cls._cache[effect] = [
                cls._render(effect, frame, FRAME_COUNT) for frame in range(FRAME_COUNT)
            ]
        return cls._cache[effect]

    @classmethod
    def frame(cls, effect: Effect, frame_index: int) -> QPixmap:
        frames = cls.frames(effect)
        return frames[frame_index % len(frames)]

    @classmethod
    def _render(cls, effect: Effect, frame: int, total: int) -> QPixmap:
        pixmap = QPixmap(PIXELS, PIXELS)
        pixmap.fill(Qt.GlobalColor.transparent)
        pixmap.setDevicePixelRatio(2.0)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        phase = frame / total

        if effect is Effect.TYPING:
            cls._typing(painter, phase)
        elif effect is Effect.NETWORK:
            cls._network(painter, phase)
        elif effect is Effect.CAMERA:
            cls._camera(painter, phase)
        elif effect is Effect.AUDIO:
            cls._audio(painter, phase)

        painter.end()
        return pixmap

    @classmethod
    def _typing(cls, painter: QPainter, phase: float) -> None:
        painter.setPen(QPen(OUTLINE, 1.5))
        painter.setBrush(DESK)
        painter.drawRoundedRect(QRectF(5.0, 72.0, 82.0, 8.0), 3.0, 3.0)
        painter.setBrush(WOOD)
        for x in (18.0, 70.0):
            painter.drawRoundedRect(QRectF(x, 78.0, 5.0, 10.0), 2.0, 2.0)

        painter.setBrush(SCREEN)
        painter.drawRoundedRect(QRectF(60.0, 46.0, 24.0, 21.0), 3.0, 3.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SCREEN_LIGHT)
        painter.drawRoundedRect(QRectF(63.0, 49.0, 18.0, 14.0), 1.5, 1.5)
        painter.setPen(QPen(QColor("#D7F4FF"), 1.0))
        for i in range(4):
            width = 6.0 + ((i * 5 + int(phase * 8)) % 8)
            painter.drawLine(
                QPointF(65.0, 52.0 + i * 3.0),
                QPointF(65.0 + width, 52.0 + i * 3.0),
            )

        painter.setPen(QPen(OUTLINE, 1.3))
        painter.setBrush(QColor("#333B46"))
        painter.drawRoundedRect(QRectF(25.0, 63.0, 38.0, 8.0), 2.0, 2.0)
        painter.setPen(QPen(QColor("#AEB8C4"), 1.0))
        for row in range(2):
            for column in range(8):
                painter.drawPoint(QPointF(28.0 + column * 4.2, 65.5 + row * 3.0))

        tap = math.sin(phase * math.tau * 2.0) * 1.5
        _arm(
            painter,
            QPointF(27.0, 45.0),
            QPointF(29.0, 56.0),
            QPointF(36.0, 64.0 + tap),
        )
        _arm(
            painter,
            QPointF(65.0, 45.0),
            QPointF(63.0, 56.0),
            QPointF(56.0, 64.0 - tap),
        )

    @classmethod
    def _network(cls, painter: QPainter, phase: float) -> None:
        _arm(
            painter,
            QPointF(27.0, 45.0),
            QPointF(30.0, 55.0),
            QPointF(26.0, 63.0),
        )

        painter.setPen(QPen(OUTLINE, 1.5))
        painter.setBrush(PHONE)
        painter.drawRoundedRect(QRectF(4.0, 46.0, 22.0, 30.0), 5.0, 5.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SCREEN_LIGHT)
        painter.drawRoundedRect(QRectF(7.0, 50.0, 16.0, 21.0), 2.0, 2.0)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(QRectF(11.0, 55.0, 8.0, 6.0), 1.5, 1.5)
        _hand(painter, QPointF(26.0, 62.0))

        _arm(
            painter,
            QPointF(66.0, 45.0),
            QPointF(71.0, 57.0),
            QPointF(72.0, 65.0),
        )

        center = QPointF(15.0, 39.0)
        for index in range(3):
            radius = 5.0 + index * 3.5 + phase * 1.5
            alpha = int(220 * (0.55 + 0.45 * math.sin(phase * math.tau + index)))
            painter.setPen(QPen(QColor(91, 192, 235, max(0, min(255, alpha))), 1.8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(
                QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2),
                125 * 16,
                110 * 16,
            )

    @classmethod
    def _camera(cls, painter: QPainter, phase: float) -> None:
        painter.setPen(QPen(OUTLINE, 1.5))
        painter.setBrush(CAMERA)
        painter.drawRoundedRect(QRectF(23.0, 47.0, 46.0, 24.0), 5.0, 5.0)
        painter.drawRoundedRect(QRectF(39.0, 42.0, 14.0, 7.0), 2.5, 2.5)

        center = QPointF(45.0, 59.0)
        painter.setBrush(QColor("#161B20"))
        painter.drawEllipse(center, 11.0, 11.0)
        painter.setBrush(LENS)
        painter.drawEllipse(center, 7.0, 7.0)
        painter.setBrush(QColor(220, 250, 255, 190))
        painter.drawEllipse(QPointF(42.5, 56.5), 2.4, 2.4)

        painter.setBrush(ACCENT)
        painter.drawRoundedRect(QRectF(63.0, 51.0, 4.0, 5.0), 1.0, 1.0)
        if math.sin(phase * math.tau * 2.0) > 0.55:
            painter.setBrush(QColor("#FF5C5C"))
            painter.drawEllipse(QPointF(64.0, 62.0), 1.8, 1.8)

        _arm(
            painter,
            QPointF(25.0, 45.0),
            QPointF(22.0, 53.0),
            QPointF(26.0, 60.0),
        )
        _arm(
            painter,
            QPointF(67.0, 45.0),
            QPointF(71.0, 53.0),
            QPointF(67.0, 60.0),
        )

    @classmethod
    def _audio(cls, painter: QPainter, phase: float) -> None:
        painter.setPen(QPen(OUTLINE, 1.5))
        painter.setBrush(MEGAPHONE)
        cone = QPainterPath(QPointF(57.0, 48.0))
        cone.lineTo(82.0, 39.0)
        cone.lineTo(82.0, 68.0)
        cone.lineTo(57.0, 58.0)
        cone.closeSubpath()
        painter.drawPath(cone)
        painter.setBrush(QColor("#C94736"))
        painter.drawRoundedRect(QRectF(51.0, 49.0, 7.0, 9.0), 2.0, 2.0)

        for index in range(3):
            radius = 4.0 + index * 3.5 + phase * 1.5
            alpha = int(220 * (0.55 + 0.45 * math.sin(phase * math.tau + index * 0.8)))
            painter.setPen(QPen(QColor(255, 209, 102, max(0, min(255, alpha))), 1.8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(
                QRectF(78.0 - radius, 54.0 - radius, radius * 2, radius * 2),
                -70 * 16,
                140 * 16,
            )

        _arm(
            painter,
            QPointF(64.0, 48.0),
            QPointF(60.0, 57.0),
            QPointF(55.0, 62.0),
        )
        _arm(
            painter,
            QPointF(27.0, 45.0),
            QPointF(22.0, 57.0),
            QPointF(23.0, 65.0 + math.sin(phase * math.tau) * 1.5),
        )
