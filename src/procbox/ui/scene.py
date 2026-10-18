from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView

from procbox import config


class PenScene(QGraphicsScene):
    """Warm, dark backdrop with a subtle grid and a rounded pen outline."""

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        gradient = QLinearGradient(
            self.sceneRect().topLeft(),
            self.sceneRect().bottomLeft(),
        )
        gradient.setColorAt(0.0, QColor("#222833"))
        gradient.setColorAt(1.0, QColor("#111419"))
        painter.fillRect(rect, gradient)

        step = 36
        left = int(rect.left()) - int(rect.left()) % step
        top = int(rect.top()) - int(rect.top()) % step
        dots = QPolygonF()
        y = top
        while y < rect.bottom():
            x = left
            while x < rect.right():
                dots.append(QPointF(x, y))
                x += step
            y += step
        painter.setPen(QPen(QColor(255, 255, 255, 12), 1.0))
        painter.drawPoints(dots)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(255, 255, 255, 20), 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.sceneRect().adjusted(9, 9, -9, -9), 22, 22)


class PenView(QGraphicsView):
    viewport_resized = Signal(QRectF)

    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        viewport = self.viewport().size()
        width = max(1.0, float(viewport.width()))
        height = max(1.0, float(viewport.height()))
        default_width = float(config.WINDOW_WIDTH)
        default_height = float(config.WINDOW_HEIGHT)

        if width >= default_width and height >= default_height:
            scale = 1.0
            scene_rect = QRectF(0.0, 0.0, width, height)
        else:
            scale = max(0.1, min(width / default_width, height / default_height))
            scene_rect = QRectF(0.0, 0.0, default_width, default_height)

        self.resetTransform()
        if scale != 1.0:
            self.scale(scale, scale)
        if self.scene() is not None:
            self.scene().setSceneRect(scene_rect)
        self.setSceneRect(scene_rect)
        self.resetCachedContent()
        self.viewport_resized.emit(scene_rect)
        self.viewport().update()
