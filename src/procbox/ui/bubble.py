from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QPainterPath,
    QPen,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import QGraphicsObject

TAIL_HEIGHT = 6.0
PADDING_X = 9.0
PADDING_Y = 6.0
MAX_TEXT_WIDTH = 230.0


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
        if parent is not None:
            parent.rotationChanged.connect(self._sync_with_parent)
            self.setRotation(-parent.rotation())

        self._font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        self._font.setPixelSize(12)
        self._font.setWeight(QFont.Weight.DemiBold)

        self._document = QTextDocument(self)
        self._document.setDocumentMargin(0.0)
        self._document.setDefaultFont(self._font)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._document.setDefaultTextOption(text_option)

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
        parent = self.parentItem()
        if parent is not None:
            self.setRotation(-parent.rotation())

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

        painter.save()
        painter.translate(PADDING_X + 1.0, PADDING_Y + 1.0)
        self._document.drawContents(painter)
        painter.restore()

    def _measure(self) -> None:
        self._document.setPlainText(self._text)
        cursor = QTextCursor(self._document)
        cursor.select(QTextCursor.SelectionType.Document)
        text_format = QTextCharFormat()
        text_format.setForeground(QColor("#3A2A22"))
        cursor.mergeCharFormat(text_format)

        self._document.setTextWidth(-1.0)
        natural_width = self._document.idealWidth()
        content_width = max(36.0, min(MAX_TEXT_WIDTH, math.ceil(natural_width) + 1.0))
        self._document.setTextWidth(content_width)
        content_height = self._document.size().height()

        self._width = content_width + PADDING_X * 2.0 + 2.0
        self._height = max(26.0, content_height + PADDING_Y * 2.0 + 2.0)

    def _place(self) -> None:
        parent = self.parentItem()
        scene = self.scene()
        if parent is None or scene is None:
            return

        scene_rect = scene.sceneRect()
        sprite_rect = parent.sceneBoundingRect()
        total_height = self._height + TAIL_HEIGHT
        space_above = sprite_rect.top() - scene_rect.top()
        space_below = scene_rect.bottom() - sprite_rect.bottom()

        if space_above >= total_height + 8.0 and space_above >= space_below:
            self._above = True
        elif space_below >= total_height + 8.0:
            self._above = False
        else:
            self._above = space_above >= space_below

        scene_left = sprite_rect.center().x() - self._width / 2.0
        min_left = scene_rect.left() + 6.0
        max_left = scene_rect.right() - self._width - 6.0
        scene_left = min(max(scene_left, min_left), max_left)

        if self._above:
            scene_top = sprite_rect.top() - total_height - 4.0
        else:
            scene_top = sprite_rect.bottom() + 4.0
        self.setPos(parent.mapFromScene(QPointF(scene_left, scene_top)))
        self.setTransformOriginPoint(
            QPointF(self._width / 2.0, self._height if self._above else 0.0)
        )

    def _sync_with_parent(self) -> None:
        parent = self.parentItem()
        if parent is None:
            return
        self.setRotation(-parent.rotation())
        if self.isVisible():
            self._place()

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
