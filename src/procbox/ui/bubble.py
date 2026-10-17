from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QGraphicsObject

from procbox import config

TAIL_HEIGHT = 6.0
PADDING_X = 9.0
PADDING_Y = 6.0
MAX_TEXT_WIDTH = 168.0


class SpeechBubble(QGraphicsObject):
    """A small comic bubble that is parented to an app sprite."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._text = ""
        self._above = True
        self._width = 60.0
        self._height = 28.0
        self._hiding = False

        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setZValue(20)

        self._font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        self._font.setPixelSize(12)
        self._font.setWeight(QFont.Weight.DemiBold)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

        self._fade = QPropertyAnimation(self, b"opacity", self)
        self._fade.finished.connect(self._on_fade_finished)
        self._pop = QPropertyAnimation(self, b"scale", self)

        self.hide()

    @property
    def is_showing(self) -> bool:
        return self.isVisible()

    def show_message(self, text: str, duration_ms: int = 2_600) -> None:
        if not text:
            return

        self._text = text
        self._measure()
        self._place()

        self._hide_timer.stop()
        self._fade.stop()
        self._pop.stop()
        self._hiding = False

        self.setOpacity(0.0)
        self.setScale(0.72)
        self.setVisible(True)
        self.setTransformOriginPoint(
            self._width / 2.0,
            self._height if self._above else 0.0,
        )

        self._pop.setDuration(280)
        self._pop.setStartValue(0.72)
        self._pop.setEndValue(1.0)
        self._pop.setEasingCurve(QEasingCurve.Type.OutBack)
        self._pop.start()

        self._fade.setDuration(160)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

        self._hide_timer.start(duration_ms)

    def hide_now(self) -> None:
        self._hide_timer.stop()
        self._fade.stop()
        self._pop.stop()
        self._hiding = False
        self.setOpacity(1.0)
        self.setScale(1.0)
        self.hide()

    def boundingRect(self) -> QRectF:
        if self._above:
            return QRectF(0.0, 0.0, self._width, self._height + TAIL_HEIGHT)
        return QRectF(0.0, -TAIL_HEIGHT, self._width, self._height + TAIL_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        body = QRectF(0.0, 0.0, self._width, self._height)
        shape = QPainterPath()
        shape.addRoundedRect(body, 9.0, 9.0)

        tail = QPainterPath()
        if self._above:
            tail.moveTo(self._width / 2.0 - 5.0, self._height - 1.0)
            tail.lineTo(self._width / 2.0, self._height + TAIL_HEIGHT)
            tail.lineTo(self._width / 2.0 + 5.0, self._height - 1.0)
        else:
            tail.moveTo(self._width / 2.0 - 5.0, 1.0)
            tail.lineTo(self._width / 2.0, -TAIL_HEIGHT)
            tail.lineTo(self._width / 2.0 + 5.0, 1.0)
        tail.closeSubpath()
        shape = shape.united(tail)

        painter.setPen(QPen(QColor("#6F5142"), 1.4))
        painter.setBrush(QColor("#FFF9EC"))
        painter.drawPath(shape)

        painter.setFont(self._font)
        painter.setPen(QColor("#3A2A22"))
        painter.drawText(
            body.adjusted(PADDING_X, PADDING_Y, -PADDING_X, -PADDING_Y),
            int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap),
            self._text,
        )

    def _measure(self) -> None:
        metrics = QFontMetricsF(self._font)
        bounds = metrics.boundingRect(
            QRectF(0.0, 0.0, MAX_TEXT_WIDTH, 200.0),
            int(Qt.TextFlag.TextWordWrap),
            self._text,
        )
        self._width = max(52.0, min(MAX_TEXT_WIDTH, bounds.width() + PADDING_X * 2.0 + 2.0))
        self._height = max(26.0, bounds.height() + PADDING_Y * 2.0 + 2.0)

    def _place(self) -> None:
        parent = self.parentItem()
        scene = self.scene()
        if parent is None or scene is None:
            return

        scene_rect = scene.sceneRect()
        parent_y = parent.pos().y()
        space_above = parent_y + config.BODY_Y - scene_rect.top()
        space_below = scene_rect.bottom() - (parent_y + config.SPRITE_LOGICAL_SIZE)
        total_height = self._height + TAIL_HEIGHT

        if space_above >= total_height + 8.0 and space_above >= space_below:
            self._above = True
        elif space_below >= total_height + 8.0:
            self._above = False
        else:
            self._above = space_above >= space_below

        desired_left = parent.pos().x() + config.SPRITE_LOGICAL_SIZE / 2.0 - self._width / 2.0
        min_left = scene_rect.left() + 6.0
        max_left = scene_rect.right() - self._width - 6.0
        scene_left = min(max(desired_left, min_left), max_left)

        y = config.BODY_Y - total_height - 2.0 if self._above else config.SPRITE_LOGICAL_SIZE - 4.0
        self.setPos(scene_left - parent.pos().x(), y)
        self.setTransformOriginPoint(
            QPointF(self._width / 2.0, self._height if self._above else 0.0)
        )

    def _fade_out(self) -> None:
        self._hiding = True
        self._fade.stop()
        self._fade.setDuration(220)
        self._fade.setStartValue(self.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._hiding:
            self._hiding = False
            self.setVisible(False)
