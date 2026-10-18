from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen


class Expression(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SURPRISED = "surprised"
    SLEEPY = "sleepy"
    ANGRY = "angry"
    SCREAM = "scream"
    DEAD = "dead"


INK = QColor("#4A2E2A")
PAPER = QColor("#FFFFFF")
HALO = QColor(255, 255, 255, 225)
BLUSH = QColor(255, 128, 150, 95)
DEAD_INK = QColor("#737373")
TONGUE = QColor("#FF8FA3")


def _stroke(painter: QPainter, color: QColor, width: float) -> None:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _draw_open_eye(
    painter: QPainter,
    center: QPointF,
    look_x: float,
    look_y: float,
    ink: QColor,
    big: bool = False,
    sleepy: bool = False,
) -> None:
    width = 6.2 if big else 5.2
    height = 7.0 if big else 6.0
    rect = QRectF(center.x() - width / 2, center.y() - height / 2, width, height)

    painter.setPen(QPen(HALO, 2.8))
    painter.setBrush(PAPER)
    painter.drawEllipse(rect)

    painter.setPen(QPen(ink, 1.1))
    painter.setBrush(PAPER)
    painter.drawEllipse(rect)

    radius = 2.3 if big else 1.9
    px = center.x() + look_x * 1.7
    py = center.y() + look_y * 1.4
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    painter.drawEllipse(QPointF(px, py), radius, radius)

    painter.setBrush(PAPER)
    painter.drawEllipse(QPointF(px - 0.7, py - 0.8), 0.6, 0.6)

    if sleepy:
        _stroke(painter, ink, 1.7)
        painter.drawLine(
            QPointF(center.x() - width / 2, center.y() - 1.0),
            QPointF(center.x() + width / 2, center.y() - 1.0),
        )


def _draw_closed_eye(painter: QPainter, center: QPointF, ink: QColor) -> None:
    path = QPainterPath(QPointF(center.x() - 3.2, center.y() + 1.0))
    path.quadTo(center.x(), center.y() - 3.6, center.x() + 3.2, center.y() + 1.0)
    _stroke(painter, HALO, 3.4)
    painter.drawPath(path)
    _stroke(painter, ink, 2.0)
    painter.drawPath(path)


def _draw_x_eye(painter: QPainter, center: QPointF, ink: QColor) -> None:
    size = 3.0
    first = QLineF(
        QPointF(center.x() - size, center.y() - size),
        QPointF(center.x() + size, center.y() + size),
    )
    second = QLineF(
        QPointF(center.x() - size, center.y() + size),
        QPointF(center.x() + size, center.y() - size),
    )
    painter.setPen(QPen(HALO, 3.4))
    painter.drawLine(first)
    painter.drawLine(second)
    painter.setPen(QPen(ink, 1.9))
    painter.drawLine(first)
    painter.drawLine(second)


def _draw_smile(painter: QPainter, center: QPointF, ink: QColor) -> None:
    path = QPainterPath(QPointF(center.x() - 4.0, center.y() - 1.0))
    path.quadTo(center.x(), center.y() + 3.0, center.x() + 4.0, center.y() - 1.0)
    _stroke(painter, HALO, 3.0)
    painter.drawPath(path)
    _stroke(painter, ink, 1.7)
    painter.drawPath(path)


def _draw_frown(painter: QPainter, center: QPointF, ink: QColor) -> None:
    path = QPainterPath(QPointF(center.x() - 4.0, center.y() + 1.5))
    path.quadTo(center.x(), center.y() - 3.0, center.x() + 4.0, center.y() + 1.5)
    _stroke(painter, HALO, 3.0)
    painter.drawPath(path)
    _stroke(painter, ink, 1.7)
    painter.drawPath(path)


def _draw_open_mouth(painter: QPainter, center: QPointF, ink: QColor) -> None:
    rect = QRectF(center.x() - 4.8, center.y() - 2.2, 9.6, 6.8)
    painter.setPen(QPen(HALO, 3.2))
    painter.setBrush(PAPER)
    painter.drawChord(rect, 180 * 16, 180 * 16)
    painter.setPen(QPen(ink, 1.1))
    painter.setBrush(ink)
    painter.drawChord(rect, 180 * 16, 180 * 16)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(TONGUE)
    painter.drawEllipse(QPointF(center.x(), center.y() + 3.0), 2.1, 1.1)


def _draw_wavy_mouth(painter: QPainter, center: QPointF, ink: QColor) -> None:
    path = QPainterPath(QPointF(center.x() - 4.0, center.y()))
    path.cubicTo(
        center.x() - 1.5,
        center.y() - 2.2,
        center.x() + 1.5,
        center.y() + 2.2,
        center.x() + 4.0,
        center.y(),
    )
    _stroke(painter, HALO, 2.9)
    painter.drawPath(path)
    _stroke(painter, ink, 1.5)
    painter.drawPath(path)


def draw_face(
    painter: QPainter,
    body: QRectF,
    expression: Expression,
    blinking: bool,
    look_x: float,
    look_y: float,
) -> None:
    """Draw a compact Q-style face on top of an app icon."""
    dead = expression is Expression.DEAD
    ink = DEAD_INK if dead else INK
    cx = body.center().x()
    eye_y = body.top() + body.height() * 0.54
    eye_dx = body.width() * 0.155
    mouth_y = body.top() + body.height() * 0.76
    eyes = (QPointF(cx - eye_dx, eye_y), QPointF(cx + eye_dx, eye_y))
    mouth = QPointF(cx, mouth_y)

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if not dead:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BLUSH)
        painter.drawEllipse(QPointF(cx - eye_dx * 1.75, mouth_y - 3.0), 4.0, 2.7)
        painter.drawEllipse(QPointF(cx + eye_dx * 1.75, mouth_y - 3.0), 4.0, 2.7)

    if expression is Expression.DEAD:
        _draw_x_eye(painter, eyes[0], ink)
        _draw_x_eye(painter, eyes[1], ink)
        _draw_wavy_mouth(painter, mouth, ink)
        painter.restore()
        return

    if blinking or expression in (Expression.HAPPY, Expression.SCREAM):
        _draw_closed_eye(painter, eyes[0], ink)
        _draw_closed_eye(painter, eyes[1], ink)
    elif expression is Expression.SURPRISED:
        _draw_open_eye(painter, eyes[0], look_x, look_y, ink, big=True)
        _draw_open_eye(painter, eyes[1], look_x, look_y, ink, big=True)
    elif expression is Expression.SLEEPY:
        _draw_open_eye(painter, eyes[0], look_x * 0.4, look_y * 0.4, ink, sleepy=True)
        _draw_open_eye(painter, eyes[1], look_x * 0.4, look_y * 0.4, ink, sleepy=True)
    else:
        _draw_open_eye(painter, eyes[0], look_x, look_y, ink)
        _draw_open_eye(painter, eyes[1], look_x, look_y, ink)

    if expression is Expression.ANGRY:
        _stroke(painter, ink, 1.8)
        painter.drawLine(
            QPointF(cx - eye_dx - 3.2, eye_y - 6.0),
            QPointF(cx - eye_dx + 3.0, eye_y - 3.6),
        )
        painter.drawLine(
            QPointF(cx + eye_dx + 3.2, eye_y - 6.0),
            QPointF(cx + eye_dx - 3.0, eye_y - 3.6),
        )
        _draw_frown(painter, mouth, ink)
    elif expression is Expression.SURPRISED:
        painter.setPen(QPen(HALO, 3.0))
        painter.setBrush(PAPER)
        painter.drawEllipse(mouth, 2.2, 2.8)
        painter.setPen(QPen(ink, 1.1))
        painter.setBrush(ink)
        painter.drawEllipse(mouth, 2.2, 2.8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(PAPER)
        painter.drawEllipse(QPointF(mouth.x() - 0.7, mouth.y() - 1.0), 0.6, 0.7)
    elif expression is Expression.SLEEPY:
        _draw_wavy_mouth(painter, mouth, ink)
        painter.setPen(QPen(ink, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        font = painter.font()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(cx + 10, eye_y - 8, 12, 10), Qt.AlignmentFlag.AlignCenter, "z")
    elif expression is Expression.SCREAM:
        painter.setPen(QPen(ink, 1.1))
        painter.setBrush(ink)
        painter.drawEllipse(QPointF(mouth.x(), mouth.y() + 1.0), 4.8, 6.2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(PAPER)
        painter.drawEllipse(QPointF(mouth.x() - 1.2, mouth.y() - 1.4), 1.0, 1.2)
        painter.setBrush(TONGUE)
        painter.drawEllipse(QPointF(mouth.x(), mouth.y() + 4.0), 2.4, 1.3)
    elif expression is Expression.HAPPY:
        _draw_open_mouth(painter, mouth, ink)
    else:
        _draw_smile(painter, mouth, ink)

    painter.restore()


def pick_expression(rng) -> Expression:
    return rng.choice(
        [
            Expression.NEUTRAL,
            Expression.HAPPY,
            Expression.HAPPY,
            Expression.SURPRISED,
            Expression.SLEEPY,
            Expression.ANGRY,
        ]
    )
