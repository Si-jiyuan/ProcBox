from __future__ import annotations

import math
import random

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsObject

from procbox import config
from procbox.core.models import AppInfo
from procbox.core.motion import Motion, random_velocity, step
from procbox.ui.bubble import SpeechBubble
from procbox.ui.face import Expression, draw_face, pick_expression

BODY = QRectF(config.BODY_X, config.BODY_Y, config.BODY_SIZE, config.BODY_SIZE)
LIMB_BLACK = QColor("#111111")
LIMB_OUTLINE = QColor("#FFFFFF")
DEAD_LIMB = QColor("#B8B8B8")
DEAD_OUTLINE = QColor("#EEEEEE")


class AppSprite(QGraphicsObject):
    """One app icon with Q-style limbs, a face and a tiny social life."""

    activated = Signal(str)

    def __init__(
        self,
        app: AppInfo,
        parent=None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(parent)
        self._app = app
        self._rng = rng or random.Random()
        self._alive = True
        self._size = config.SPRITE_LOGICAL_SIZE
        self._icon_png = app.icon_png
        self._color_pixmap = self._build_pixmap(app)
        self._gray_pixmap: QPixmap | None = None

        vx, vy = random_velocity(self._rng)
        self._motion = Motion(0.0, 0.0, vx, vy)
        self._anim_time = self._rng.uniform(0.0, 8.0)
        self._move_phase = self._rng.uniform(0.0, math.tau)

        self._expression = Expression.NEUTRAL
        self._expression_timer = self._rng.uniform(2.5, 6.0)
        self._blink_timer = self._rng.uniform(1.5, 4.5)
        self._blink_remaining = 0.0
        self._look_x = 0.0
        self._look_y = 0.0
        self._look_target_x = 0.0
        self._look_target_y = 0.0
        self._look_timer = self._rng.uniform(1.5, 4.0)

        self._rest_countdown = self._rng.uniform(5.0, 11.0)
        self._rest_remaining = 0.0
        self._chatting = False
        self._fighting = False
        self._facing = self._rng.choice((-1.0, 1.0))

        self._bubble = SpeechBubble(self)

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setTransformOriginPoint(self._size / 2.0, self._size / 2.0)
        self.setToolTip(self._tooltip())

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22.0)
        shadow.setOffset(0.0, 7.0)
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
    def is_resting(self) -> bool:
        return self._rest_remaining > 0.0

    @property
    def is_chatting(self) -> bool:
        return self._chatting

    @property
    def is_fighting(self) -> bool:
        return self._fighting

    @property
    def is_saying(self) -> bool:
        return self._bubble.is_showing

    @property
    def expression(self) -> Expression:
        return self._expression

    @property
    def size(self) -> float:
        return self._size

    @property
    def center_scene(self) -> QPointF:
        return QPointF(
            self.pos().x() + BODY.center().x(),
            self.pos().y() + BODY.center().y(),
        )

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, self._size, self._size)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if not self._alive:
            bob = 0.0
            sway = 0.0
            tilt = 0.0
        elif self._fighting:
            bob = -abs(math.sin(self._anim_time * 16.0)) * 2.6
            sway = math.sin(self._anim_time * 23.0) * 2.2
            tilt = math.sin(self._anim_time * 19.0) * 5.0
        elif self._chatting:
            bob = -abs(math.sin(self._anim_time * 5.2)) * 3.0
            sway = math.sin(self._anim_time * 2.5) * 0.6
            tilt = math.sin(self._anim_time * 2.5) * 1.5
        elif self.is_resting:
            bob = math.sin(self._anim_time * 2.1) * 1.0
            sway = math.sin(self._anim_time * 1.3) * 0.5
            tilt = math.sin(self._anim_time * 1.3) * 2.0
        else:
            wobble = self._move_phase * 0.55
            bob = -abs(math.sin(self._move_phase)) * 2.2
            sway = math.sin(wobble) * 1.5 + math.sin(wobble * 2.3) * 0.4
            tilt = math.sin(wobble) * 2.6

        center = BODY.center()
        painter.save()
        painter.translate(sway, bob)
        painter.translate(center)
        painter.rotate(tilt)
        painter.translate(-center)

        self._draw_limbs(painter)
        pixmap = self._color_pixmap if self._alive else (self._gray_pixmap or self._color_pixmap)
        painter.drawPixmap(BODY.topLeft(), pixmap)
        draw_face(
            painter,
            BODY,
            self._expression,
            self._blink_remaining > 0.0,
            self._look_x,
            self._look_y,
        )
        painter.restore()

    def place(self, x: float, y: float) -> None:
        self._motion = Motion(x, y, self._motion.vx, self._motion.vy)
        self.setPos(x, y)
        self.setZValue(y + self._size)

    def advance(self, dt: float, width: float, height: float) -> None:
        if not self._alive:
            return

        self._anim_time += dt
        self._tick_face(dt)
        self.update()

        if self._chatting or self._fighting:
            return

        if self._rest_remaining > 0.0:
            self._rest_remaining -= dt
            if self._rest_remaining <= 0.0:
                self._wake_up()
            return

        self._rest_countdown -= dt
        if self._rest_countdown <= 0.0:
            self._start_rest()
            return

        self._move_phase += dt * (3.5 + self._motion.speed / 18.0)
        self._motion = step(self._motion, dt, width, height, self._size, self._rng)
        self.setPos(self._motion.x, self._motion.y)
        self.setZValue(self._motion.y + self._size)

        if self._motion.speed > 0.0:
            self._look_target_x = self._motion.vx / self._motion.speed * 0.85
            self._look_target_y = self._motion.vy / self._motion.speed * 0.85
        if abs(self._motion.vx) > 1.0:
            self._facing = 1.0 if self._motion.vx > 0.0 else -1.0

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

    def begin_chat(self) -> None:
        if not self._alive:
            return
        self._fighting = False
        self._chatting = True
        self._rest_remaining = 0.0
        self._expression = Expression.HAPPY
        self._expression_timer = 99.0

    def end_chat(self) -> None:
        if not self._alive:
            return
        self._chatting = False
        self._expression = Expression.HAPPY
        self._expression_timer = self._rng.uniform(2.0, 4.5)
        self._wake_up()

    def begin_fight(self, opponent: QPointF) -> None:
        if not self._alive:
            return
        self._fighting = True
        self._chatting = False
        self._rest_remaining = 0.0
        self._expression = Expression.ANGRY
        self._expression_timer = 99.0
        self.look_toward(opponent)

    def end_fight(self) -> None:
        if not self._alive:
            return
        self._fighting = False
        self._expression = self._rng.choice(
            [Expression.HAPPY, Expression.SURPRISED, Expression.SLEEPY]
        )
        self._expression_timer = self._rng.uniform(2.0, 4.5)
        self._wake_up()

    def look_toward(self, scene_point: QPointF) -> None:
        center = self.center_scene
        dx = scene_point.x() - center.x()
        dy = scene_point.y() - center.y()
        if abs(dx) > 2.0:
            self._facing = 1.0 if dx > 0.0 else -1.0
        length = math.hypot(dx, dy)
        if length == 0.0:
            self._look_target_x = 0.0
            self._look_target_y = 0.0
            return
        self._look_target_x = dx / length * 1.2
        self._look_target_y = dy / length * 1.2

    def move_center_to(self, scene_point: QPointF) -> None:
        self.place(
            scene_point.x() - BODY.center().x(),
            scene_point.y() - BODY.center().y(),
        )

    def say(self, text: str, duration_ms: int = 2_600) -> None:
        if self._alive:
            self._bubble.show_message(text, duration_ms)

    def die(self) -> None:
        if not self._alive:
            return
        self._alive = False
        self._chatting = False
        self._fighting = False
        self._rest_remaining = 0.0
        self._expression = Expression.DEAD
        self._blink_remaining = 0.0
        self._bubble.hide_now()
        self._scale_anim.stop()
        self.setScale(1.0)
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
        self._expression = Expression.HAPPY
        self._expression_timer = self._rng.uniform(2.0, 4.5)
        self._blink_timer = self._rng.uniform(1.0, 3.0)
        self._rest_countdown = self._rng.uniform(4.0, 9.0)
        self._gray_pixmap = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._tooltip())
        self.update()

        vx, vy = random_velocity(self._rng)
        self._motion = Motion(self._motion.x, self._motion.y, vx, vy)
        if abs(vx) > 1.0:
            self._facing = 1.0 if vx > 0.0 else -1.0
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

    def _tick_face(self, dt: float) -> None:
        if self._blink_remaining > 0.0:
            self._blink_remaining -= dt
        else:
            self._blink_timer -= dt
            if self._blink_timer <= 0.0:
                self._blink_remaining = 0.12
                self._blink_timer = self._rng.uniform(2.2, 6.0)

        if not self._chatting:
            self._expression_timer -= dt
            if self._expression_timer <= 0.0:
                self._expression = pick_expression(self._rng)
                self._expression_timer = self._rng.uniform(3.5, 8.0)

        if self.is_resting and not self._chatting:
            self._look_timer -= dt
            if self._look_timer <= 0.0:
                angle = self._rng.uniform(0.0, math.tau)
                self._look_target_x = math.cos(angle)
                self._look_target_y = math.sin(angle)
                self._look_timer = self._rng.uniform(1.2, 3.5)

        blend = min(1.0, dt * 10.0)
        self._look_x += (self._look_target_x - self._look_x) * blend
        self._look_y += (self._look_target_y - self._look_y) * blend

    def _start_rest(self) -> None:
        self._rest_remaining = self._rng.uniform(1.8, 3.8)
        self._rest_countdown = 1_000_000.0
        self._expression = self._rng.choice(
            [Expression.SLEEPY, Expression.HAPPY, Expression.NEUTRAL]
        )
        self._expression_timer = self._rest_remaining
        self._look_timer = self._rng.uniform(0.4, 1.5)

    def _wake_up(self) -> None:
        vx, vy = random_velocity(self._rng)
        self._motion = Motion(self._motion.x, self._motion.y, vx, vy)
        if abs(vx) > 1.0:
            self._facing = 1.0 if vx > 0.0 else -1.0
        self._rest_remaining = 0.0
        self._rest_countdown = self._rng.uniform(6.0, 14.0)
        self._expression_timer = self._rng.uniform(2.0, 4.5)
        self.setZValue(self._motion.y + self._size)

    def _draw_limbs(self, painter: QPainter) -> None:
        dead = not self._alive
        limb_color = DEAD_LIMB if dead else LIMB_BLACK
        outline_color = DEAD_OUTLINE if dead else LIMB_OUTLINE
        cx = BODY.center().x()
        pivot = QPointF(self._size / 2.0, self._size / 2.0)
        theta = math.radians(self.rotation()) if dead else 0.0

        if dead or self._chatting or self._fighting or self.is_resting:
            arm_swing = 0.0
            walking = False
        else:
            arm_swing = math.sin(self._move_phase) * 9.0
            walking = True

        def to_world(point: QPointF) -> QPointF:
            return self._rotate_point(point, pivot, theta)

        def to_local(point: QPointF) -> QPointF:
            return self._rotate_point(point, pivot, -theta)

        for side in (-1, 1):
            hip = QPointF(cx + side * 9.5, BODY.bottom() - 6.0)

            if dead:
                hip_world = to_world(hip)
                ankle_world = QPointF(hip_world.x() + side * 2.0, hip_world.y() + 16.0)
                toe_world = QPointF(
                    ankle_world.x() + self._facing * 8.0,
                    ankle_world.y(),
                )
                ankle = to_local(ankle_world)
                toe = to_local(toe_world)
            else:
                leg_phase = self._move_phase + (0.0 if side < 0 else math.pi)
                stride = math.sin(leg_phase) * 4.0 if walking else 0.0
                lift = max(0.0, math.sin(leg_phase)) * 4.0 if walking else 0.0
                ankle_y = 79.0 if walking else 80.0
                if self._chatting:
                    ankle_y -= abs(math.sin(self._anim_time * 5.0 + side)) * 3.0
                elif self._fighting:
                    ankle_y -= abs(math.sin(self._anim_time * 14.0 + side)) * 4.0
                ankle = QPointF(cx + side * 11.0 + stride, ankle_y - lift)
                toe = QPointF(ankle.x() + self._facing * 8.0, ankle.y())

            leg = QPainterPath(hip)
            leg.lineTo(ankle)
            leg.lineTo(toe)
            self._stroke_path(painter, leg, outline_color, 7.0)
            self._stroke_path(painter, leg, limb_color, 4.4)

        for side in (-1, 1):
            shoulder = QPointF(cx + side * 20.0, BODY.top() + 36.0)

            if dead:
                shoulder_world = to_world(shoulder)
                hand_world = QPointF(
                    shoulder_world.x() + side * 4.0,
                    shoulder_world.y() + 20.0,
                )
                control_world = QPointF(
                    (shoulder_world.x() + hand_world.x()) / 2.0 + side * 3.0,
                    shoulder_world.y() + 10.0,
                )
                hand = to_local(hand_world)
                control = to_local(control_world)
            else:
                if self._chatting:
                    wave = math.sin(self._anim_time * 7.0 + side) * 3.0
                    hand = QPointF(cx + side * 38.0, BODY.top() + 12.0 + wave)
                    control = QPointF(cx + side * 34.0, 48.0)
                elif self._fighting:
                    punch = math.sin(self._anim_time * 24.0 + (0.0 if side < 0 else math.pi))
                    hand = QPointF(
                        cx + self._facing * (34.0 + punch * 4.0),
                        50.0 + side * 4.0 + punch * 4.0,
                    )
                    control = QPointF(cx + self._facing * 28.0, 46.0 + side * 4.0)
                elif walking:
                    hand = QPointF(cx + side * 36.0, 56.0 + side * arm_swing * 0.55)
                    control = QPointF(cx + side * 34.0, 48.0)
                else:
                    hand = QPointF(cx + side * 34.0, 58.0 + side * arm_swing * 0.3)
                    control = QPointF(cx + side * 34.0, 48.0)

            arm = QPainterPath(shoulder)
            arm.quadTo(control, hand)
            self._stroke_path(painter, arm, outline_color, 6.4)
            self._stroke_path(painter, arm, limb_color, 4.0)

            painter.setPen(QPen(outline_color, 1.5))
            painter.setBrush(limb_color)
            painter.drawEllipse(hand, 3.6, 3.6)

    @staticmethod
    def _rotate_point(point: QPointF, pivot: QPointF, angle: float) -> QPointF:
        if angle == 0.0:
            return point
        cosine = math.cos(angle)
        sine = math.sin(angle)
        dx = point.x() - pivot.x()
        dy = point.y() - pivot.y()
        return QPointF(
            pivot.x() + dx * cosine - dy * sine,
            pivot.y() + dx * sine + dy * cosine,
        )

    @staticmethod
    def _stroke_path(painter: QPainter, path: QPainterPath, color: QColor, width: float) -> None:
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

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
