from __future__ import annotations

import math
import random
from enum import Enum

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsObject

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
GROAN_LINES = ["呃…", "啊…", "唔…", "好痛…", "咳…"]


class LyingPose(Enum):
    PRONE = "prone"
    SUPINE = "supine"


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
        self._face_cache: QPixmap | None = None
        self._face_cache_key: tuple | None = None

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
        self._spectating = False
        self._helping = False
        self._fleeing = False
        self._chasing = False
        self._caring = False
        self._watch_target: QPointF | None = None
        self._watch_focus: QPointF | None = None
        self._chase_target: AppSprite | None = None
        self._flee_vx = 0.0
        self._flee_vy = 0.0
        self._chase_delay = 0.0
        self._facing = self._rng.choice((-1.0, 1.0))
        self._grudge_remaining = 0.0
        self._wound_side = self._rng.choice((-1.0, 1.0))
        self._knocked_down = False
        self._lying_pose = LyingPose.PRONE
        self._down_remaining = 0.0
        self._down_groan_timer = 0.0

        self._bubble = SpeechBubble(self)

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setTransformOriginPoint(self._size / 2.0, self._size / 2.0)
        self.setToolTip(self._tooltip())

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
    def is_spectating(self) -> bool:
        return self._spectating

    @property
    def is_knocked_down(self) -> bool:
        return self._knocked_down

    @property
    def lying_pose(self) -> LyingPose:
        return self._lying_pose

    @property
    def is_helping(self) -> bool:
        return self._helping

    @property
    def is_gathering(self) -> bool:
        return self._spectating and self._watch_target is not None

    @property
    def is_caring(self) -> bool:
        return self._caring

    @property
    def is_fleeing(self) -> bool:
        return self._fleeing

    @property
    def is_chasing(self) -> bool:
        return self._chasing

    @property
    def is_saying(self) -> bool:
        return self._bubble.is_showing

    @property
    def is_grudging(self) -> bool:
        return self._grudge_remaining > 0.0

    @property
    def grudge_remaining(self) -> float:
        return self._grudge_remaining

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

        if not self._alive or self._knocked_down:
            bob = 0.0
            sway = 0.0
            tilt = 0.0
        elif self._fighting:
            bob = -abs(math.sin(self._anim_time * 16.0)) * 2.6
            sway = math.sin(self._anim_time * 23.0) * 2.2
            tilt = math.sin(self._anim_time * 19.0) * 5.0
        elif self._spectating:
            if self.is_gathering:
                wobble = self._move_phase * 0.55
                bob = -abs(math.sin(self._move_phase)) * 2.2
                sway = math.sin(wobble) * 1.2
                tilt = math.sin(wobble) * 2.0
            else:
                bob = -abs(math.sin(self._anim_time * 4.8)) * 2.4
                sway = math.sin(self._anim_time * 3.2) * 0.9
                tilt = math.sin(self._anim_time * 2.2) * 2.2
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

        self._draw_shadow(painter)
        self._draw_limbs(painter)
        pixmap = self._color_pixmap if self._alive else (self._gray_pixmap or self._color_pixmap)
        painter.drawPixmap(BODY.topLeft(), pixmap)
        self._draw_face_cached(painter)
        self._draw_wound(painter)
        painter.restore()

    def place(self, x: float, y: float) -> None:
        self._motion = Motion(x, y, self._motion.vx, self._motion.vy)
        self.setPos(x, y)
        self.setZValue(y + self._size)

    def advance(
        self,
        dt: float,
        width: float,
        height: float,
        avoid_zone: tuple[QPointF, float] | None = None,
    ) -> None:
        if not self._alive:
            return

        self._anim_time += dt
        if self._knocked_down:
            self._tick_down(dt)
            return

        self._tick_face(dt)

        if self._fleeing or self._chasing:
            self._tick_run(dt, width, height)
            return

        if self._caring:
            self._move_phase += dt * 8.0
            return

        if self._spectating:
            if self._watch_target is not None:
                self._tick_gather(dt, width, height)
            else:
                self.update()
            return

        if self._chatting or self._fighting:
            self.update()
            return

        if self._rest_remaining > 0.0:
            self._rest_remaining -= dt
            self.update()
            if self._rest_remaining <= 0.0:
                self._wake_up()
            return

        self._rest_countdown -= dt
        if self._rest_countdown <= 0.0:
            self.update()
            self._start_rest()
            return

        self._move_phase += dt * (3.5 + self._motion.speed / 18.0)
        self._motion = step(self._motion, dt, width, height, self._size, self._rng)
        if avoid_zone is not None:
            self._steer_around(avoid_zone, width, height)
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
        if not self._alive or self._knocked_down:
            return
        self._fighting = False
        self._spectating = False
        self._helping = False
        self._fleeing = False
        self._chasing = False
        self._caring = False
        self._watch_target = None
        self._watch_focus = None
        self._chase_target = None
        self._chatting = True
        self._rest_remaining = 0.0
        self._expression = Expression.HAPPY
        self._expression_timer = 99.0

    def end_chat(self) -> None:
        if not self._alive:
            return
        self._chatting = False
        if self.is_grudging:
            self._expression = Expression.ANGRY
            self._expression_timer = self._grudge_remaining
        else:
            self._expression = Expression.HAPPY
            self._expression_timer = self._rng.uniform(2.0, 4.5)
        self._wake_up()

    def begin_fight(self, opponent: QPointF) -> None:
        if not self._alive or self._knocked_down:
            return
        self._fighting = True
        self._chatting = False
        self._spectating = False
        self._helping = False
        self._fleeing = False
        self._chasing = False
        self._caring = False
        self._watch_target = None
        self._watch_focus = None
        self._chase_target = None
        self._rest_remaining = 0.0
        self._expression = Expression.ANGRY
        self._expression_timer = 99.0
        self.look_toward(opponent)

    def end_fight(self) -> None:
        if not self._alive:
            return
        self._fighting = False
        self._grudge_remaining = self._rng.uniform(5.0, 60.0)
        self._wound_side = self._rng.choice((-1.0, 1.0))
        self._expression = Expression.ANGRY
        self._expression_timer = self._grudge_remaining
        self._wake_up()

    def knock_down(
        self,
        duration: float | None = None,
        pose: LyingPose | None = None,
    ) -> None:
        if not self._alive:
            return
        self._knocked_down = True
        self._lying_pose = pose or self._rng.choice([LyingPose.PRONE, LyingPose.SUPINE])
        self._chatting = False
        self._fighting = False
        self._spectating = False
        self._helping = False
        self._fleeing = False
        self._chasing = False
        self._chase_target = None
        self._rest_remaining = 0.0
        self._down_remaining = duration if duration is not None else self._rng.uniform(15.0, 60.0)
        self._down_groan_timer = self._rng.uniform(3.0, 6.0)
        self._expression = Expression.SLEEPY
        self._expression_timer = 999.0
        self._blink_remaining = 0.0
        self._bubble.hide_now()
        self._scale_anim.stop()
        self.setScale(1.0)
        self.say(self._rng.choice(GROAN_LINES), 2_000)
        self.update()

        self._fall_anim.stop()
        if self._lying_pose is LyingPose.PRONE:
            target = self._rng.choice((-1.0, 1.0)) * self._rng.uniform(80.0, 94.0)
        else:
            target = 90.0 + self._rng.uniform(-8.0, 8.0)
        self._fall_anim.setDuration(620)
        self._fall_anim.setStartValue(self.rotation())
        self._fall_anim.setEndValue(target)
        self._fall_anim.setEasingCurve(QEasingCurve.Type.OutBounce)
        self._fall_anim.start()

    def get_up(self) -> None:
        if not self._knocked_down:
            return
        self._knocked_down = False
        self._down_remaining = 0.0
        self._bubble.hide_now()
        if self.is_grudging:
            self._expression = Expression.ANGRY
            self._expression_timer = self._grudge_remaining
        else:
            self._expression = Expression.HAPPY
            self._expression_timer = self._rng.uniform(2.0, 4.5)
        self.update()

        self._fall_anim.stop()
        self._fall_anim.setDuration(420)
        self._fall_anim.setStartValue(self.rotation())
        self._fall_anim.setEndValue(0.0)
        self._fall_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._fall_anim.start()
        self._wake_up()

    def begin_watch(self, focus: QPointF) -> None:
        if not self._alive or self._knocked_down:
            return
        self._spectating = True
        self._helping = False
        self._chatting = False
        self._fighting = False
        self._fleeing = False
        self._chasing = False
        self._caring = False
        self._chase_target = None
        self._rest_remaining = 0.0
        self._expression = self._rng.choice([Expression.SURPRISED, Expression.HAPPY])
        self._expression_timer = 99.0
        self._watch_focus = focus
        self._watch_target = None
        self.look_toward(focus)

    def begin_help(self, focus: QPointF) -> None:
        if not self._alive or self._knocked_down:
            return
        self._spectating = True
        self._helping = True
        self._chatting = False
        self._fighting = False
        self._fleeing = False
        self._chasing = False
        self._caring = False
        self._chase_target = None
        self._rest_remaining = 0.0
        self._expression = Expression.ANGRY
        self._expression_timer = 99.0
        self._watch_focus = focus
        self.look_toward(focus)

    def set_watch_target(self, target: QPointF, width: float, height: float) -> None:
        if not self._spectating:
            return
        min_x = BODY.center().x()
        max_x = max(min_x, width - (self._size - BODY.center().x()))
        min_y = BODY.center().y()
        max_y = max(min_y, height - (self._size - BODY.center().y()))
        self._watch_target = QPointF(
            min(max(target.x(), min_x), max_x),
            min(max(target.y(), min_y), max_y),
        )

    def end_watch(self) -> None:
        if not self._alive:
            return
        self._spectating = False
        self._helping = False
        self._watch_target = None
        self._watch_focus = None
        if not self.is_grudging:
            self._expression = self._rng.choice([Expression.HAPPY, Expression.SURPRISED])
        self._wake_up()

    def begin_care(self, focus: QPointF) -> None:
        if not self._alive or self._knocked_down:
            return
        self._caring = True
        self._chatting = False
        self._fighting = False
        self._spectating = False
        self._helping = False
        self._fleeing = False
        self._chasing = False
        self._chase_target = None
        self._watch_target = None
        self._watch_focus = None
        self._rest_remaining = 0.0
        self._expression = self._rng.choice([Expression.SURPRISED, Expression.HAPPY])
        self._expression_timer = 99.0
        self._bubble.hide_now()
        self.look_toward(focus)

    def end_care(self) -> None:
        if not self._caring:
            return
        self._caring = False
        self._expression = Expression.HAPPY
        self._expression_timer = self._rng.uniform(2.0, 4.5)
        self._wake_up()

    def start_flee(self, away_from: QPointF, direction: QPointF | None = None) -> None:
        if not self._alive or self._knocked_down:
            return
        self._fleeing = True
        self._chasing = False
        self._chase_target = None
        self._chatting = False
        self._fighting = False
        self._spectating = False
        self._helping = False
        self._caring = False
        self._watch_target = None
        self._watch_focus = None
        self._rest_remaining = 0.0
        self._expression = Expression.ANGRY
        self._expression_timer = 99.0

        center = self.center_scene
        if direction is not None and (direction.x() != 0.0 or direction.y() != 0.0):
            length = math.hypot(direction.x(), direction.y())
            ux, uy = direction.x() / length, direction.y() / length
        else:
            dx = center.x() - away_from.x()
            dy = center.y() - away_from.y()
            length = math.hypot(dx, dy)
            if length < 1e-6:
                angle = self._rng.uniform(0.0, math.tau)
                ux, uy = math.cos(angle), math.sin(angle)
            else:
                ux, uy = dx / length, dy / length
        speed = 145.0
        self._flee_vx = ux * speed
        self._flee_vy = uy * speed
        self._facing = 1.0 if ux >= 0.0 else -1.0
        self._bubble.hide_now()
        self.say("溜了溜了！", 1_300)

    def start_chase(self, target: AppSprite, delay: float = 0.0) -> None:
        if not self._alive or self._knocked_down:
            return
        self._chasing = True
        self._fleeing = False
        self._chase_target = target
        self._chase_delay = delay
        self._chatting = False
        self._fighting = False
        self._spectating = False
        self._helping = False
        self._caring = False
        self._watch_target = None
        self._watch_focus = None
        self._rest_remaining = 0.0
        self._expression = Expression.ANGRY
        self._expression_timer = 99.0
        self._bubble.hide_now()

    def end_chase(self) -> None:
        if not self._fleeing and not self._chasing:
            return
        self._fleeing = False
        self._chasing = False
        self._chase_target = None
        self._chase_delay = 0.0
        self._bubble.hide_now()
        self._wake_up()
        self._expression = Expression.ANGRY
        self._expression_timer = max(6.0, self._grudge_remaining)

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

    def die(self, pose: LyingPose | None = None) -> None:
        if not self._alive:
            return
        self._alive = False
        self._lying_pose = pose or self._rng.choice([LyingPose.PRONE, LyingPose.SUPINE])
        self._chatting = False
        self._fighting = False
        self._spectating = False
        self._helping = False
        self._fleeing = False
        self._chasing = False
        self._caring = False
        self._watch_target = None
        self._watch_focus = None
        self._chase_target = None
        self._knocked_down = False
        self._down_remaining = 0.0
        self._rest_remaining = 0.0
        self._expression = Expression.DEAD
        self._blink_remaining = 0.0
        self._bubble.hide_now()
        self._grudge_remaining = 0.0
        self._scale_anim.stop()
        self.setScale(1.0)
        self._gray_pixmap = self._to_grayscale(self._color_pixmap)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip(f"{self._app.name}\n已关闭")
        self.update()

        self._fall_anim.stop()
        if self._lying_pose is LyingPose.PRONE:
            target = self._rng.choice((-1.0, 1.0)) * self._rng.uniform(72.0, 96.0)
        else:
            target = 90.0 + self._rng.uniform(-8.0, 8.0)
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
        self._spectating = False
        self._helping = False
        self._fleeing = False
        self._chasing = False
        self._caring = False
        self._watch_target = None
        self._watch_focus = None
        self._chase_target = None
        self._knocked_down = False
        self._down_remaining = 0.0
        self._grudge_remaining = 0.0
        self._wound_side = self._rng.choice((-1.0, 1.0))
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
            self.setToolTip(self._tooltip())
            if not self._knocked_down:
                self._animate_scale(1.08, 130)
        event.accept()

    def hoverLeaveEvent(self, event) -> None:
        self._animate_scale(1.0, 160)
        event.accept()

    def _face_key(self) -> tuple:
        return (
            self._expression,
            self._blink_remaining > 0.0 or self._knocked_down,
            round(self._look_x * 5.0) / 5.0,
            round(self._look_y * 5.0) / 5.0,
        )

    def _draw_face_cached(self, painter: QPainter) -> None:
        key = self._face_key()
        if self._face_cache is None or key != self._face_cache_key:
            cache = QPixmap(config.ICON_PIXELS, config.ICON_PIXELS)
            cache.fill(Qt.GlobalColor.transparent)
            cache.setDevicePixelRatio(2.0)
            cache_painter = QPainter(cache)
            cache_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            draw_face(
                cache_painter,
                QRectF(0.0, 0.0, config.BODY_SIZE, config.BODY_SIZE),
                self._expression,
                self._blink_remaining > 0.0 or self._knocked_down,
                self._look_x,
                self._look_y,
            )
            cache_painter.end()
            self._face_cache = cache
            self._face_cache_key = key
        painter.drawPixmap(BODY.topLeft(), self._face_cache)

    def _draw_shadow(self, painter: QPainter) -> None:
        shadow = QRectF(BODY.x() + 4.0, BODY.bottom() - 3.0, BODY.width() - 8.0, 14.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 40))
        painter.drawEllipse(shadow)
        painter.setBrush(QColor(0, 0, 0, 45))
        painter.drawEllipse(shadow.adjusted(7.0, 2.0, -7.0, 0.0))

    def _tick_face(self, dt: float) -> None:
        if self._blink_remaining > 0.0:
            self._blink_remaining -= dt
        else:
            self._blink_timer -= dt
            if self._blink_timer <= 0.0:
                self._blink_remaining = 0.12
                self._blink_timer = self._rng.uniform(2.2, 6.0)

        if self._fighting or self._helping or self._fleeing or self._chasing:
            self._expression = Expression.ANGRY
            self._expression_timer = 99.0
        elif self._grudge_remaining > 0.0:
            self._grudge_remaining = max(0.0, self._grudge_remaining - dt)
            if self._grudge_remaining > 0.0:
                if not self._chatting and not self._spectating and not self._caring:
                    self._expression = Expression.ANGRY
                    self._expression_timer = self._grudge_remaining
            else:
                self._expression_timer = 0.0
        elif not self._chatting:
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

    def _tick_gather(self, dt: float, width: float, height: float) -> None:
        target = self._watch_target
        if target is None:
            return
        center = self.center_scene
        dx = target.x() - center.x()
        dy = target.y() - center.y()
        distance = math.hypot(dx, dy)
        if distance <= 5.0:
            self._watch_target = None
            x = target.x() - BODY.center().x()
            y = target.y() - BODY.center().y()
            self._motion = Motion(x, y, 0.0, 0.0)
            self.setPos(x, y)
            self.setZValue(y + self._size)
            if self._watch_focus is not None:
                self.look_toward(self._watch_focus)
            return

        step = min(distance, 115.0 * dt)
        ux = dx / distance
        uy = dy / distance
        max_x = max(0.0, width - self._size)
        max_y = max(0.0, height - self._size)
        x = center.x() + ux * step - BODY.center().x()
        y = center.y() + uy * step - BODY.center().y()
        x = min(max(x, 0.0), max_x)
        y = min(max(y, 0.0), max_y)
        self._motion = Motion(x, y, ux * 115.0, uy * 115.0)
        self.setPos(x, y)
        self.setZValue(y + self._size)
        self._move_phase += dt * 9.0
        if abs(ux) > 0.05:
            self._facing = 1.0 if ux > 0.0 else -1.0
        self._look_target_x = ux
        self._look_target_y = uy

    def _tick_run(self, dt: float, width: float, height: float) -> None:
        if self._fleeing:
            vx = self._flee_vx
            vy = self._flee_vy
        elif self._chasing and self._chase_target is not None:
            if self._chase_delay > 0.0:
                self._chase_delay = max(0.0, self._chase_delay - dt)
                return
            target = self._chase_target
            if not target.is_alive:
                self.end_chase()
                return
            dx = target.center_scene.x() - self.center_scene.x()
            dy = target.center_scene.y() - self.center_scene.y()
            distance = math.hypot(dx, dy)
            if distance < 1e-6:
                return
            speed = 90.0
            vx = dx / distance * speed
            vy = dy / distance * speed
        else:
            return

        x = self.pos().x() + vx * dt
        y = self.pos().y() + vy * dt
        max_x = max(0.0, width - self._size)
        max_y = max(0.0, height - self._size)

        if self._fleeing:
            if x < 0.0:
                x = 0.0
                vx = abs(vx)
            elif x > max_x:
                x = max_x
                vx = -abs(vx)
            if y < 0.0:
                y = 0.0
                vy = abs(vy)
            elif y > max_y:
                y = max_y
                vy = -abs(vy)
            self._flee_vx = vx
            self._flee_vy = vy
        else:
            x = min(max(x, 0.0), max_x)
            y = min(max(y, 0.0), max_y)

        self._motion = Motion(x, y, vx, vy)
        self.setPos(x, y)
        self.setZValue(y + self._size)
        self._move_phase += dt * 12.0
        if abs(vx) > 1.0:
            self._facing = 1.0 if vx > 0.0 else -1.0
        speed = math.hypot(vx, vy)
        if speed > 0.0:
            self._look_target_x = vx / speed
            self._look_target_y = vy / speed

    def _tick_down(self, dt: float) -> None:
        self._down_remaining -= dt
        if self._grudge_remaining > 0.0:
            self._grudge_remaining = max(0.0, self._grudge_remaining - dt)

        self._down_groan_timer -= dt
        if self._down_groan_timer <= 0.0:
            if not self.is_saying:
                self.say(self._rng.choice(GROAN_LINES), 1_600)
            self._down_groan_timer = self._rng.uniform(7.0, 12.0)

        if self._down_remaining <= 0.0:
            self.get_up()

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
        if self.is_grudging:
            self._expression = Expression.ANGRY
            self._expression_timer = self._grudge_remaining
        else:
            self._expression_timer = self._rng.uniform(2.0, 4.5)
        self.setZValue(self._motion.y + self._size)

    def _steer_around(
        self,
        avoid_zone: tuple[QPointF, float],
        width: float,
        height: float,
    ) -> None:
        center, radius = avoid_zone
        sprite_center_x = self._motion.x + BODY.center().x()
        sprite_center_y = self._motion.y + BODY.center().y()
        dx = sprite_center_x - center.x()
        dy = sprite_center_y - center.y()
        distance = math.hypot(dx, dy)
        if distance >= radius:
            return

        if distance < 1e-6:
            angle = self._rng.uniform(0.0, math.tau)
            ux, uy = math.cos(angle), math.sin(angle)
        else:
            ux, uy = dx / distance, dy / distance

        push = radius - distance
        x = self._motion.x + ux * push
        y = self._motion.y + uy * push
        max_x = max(0.0, width - self._size)
        max_y = max(0.0, height - self._size)
        x = min(max(x, 0.0), max_x)
        y = min(max(y, 0.0), max_y)

        vx = self._motion.vx
        vy = self._motion.vy
        inward = vx * ux + vy * uy
        if inward < 0.0:
            vx -= 2.0 * inward * ux
            vy -= 2.0 * inward * uy

        tangent = ux * vy - uy * vx
        if abs(tangent) < 4.0:
            sign = 1.0 if self._rng.random() < 0.5 else -1.0
            vx += -uy * 10.0 * sign
            vy += ux * 10.0 * sign

        self._motion = Motion(x, y, vx, vy)
        self._look_target_x = ux
        self._look_target_y = uy

    def _draw_limbs(self, painter: QPainter) -> None:
        dead = not self._alive
        limb_color = DEAD_LIMB if dead else LIMB_BLACK
        outline_color = DEAD_OUTLINE if dead else LIMB_OUTLINE
        cx = BODY.center().x()
        static = dead or self._knocked_down
        pivot = QPointF(self._size / 2.0, self._size / 2.0)
        theta = math.radians(self.rotation()) if static else 0.0

        cheering = self._chatting or (self._spectating and not self.is_gathering)
        if static or cheering or self._fighting or self.is_resting:
            arm_swing = 0.0
            walking = False
        else:
            arm_swing = math.sin(self._move_phase) * 9.0
            walking = True

        for side in (-1, 1):
            hip = QPointF(cx + side * 9.5, BODY.bottom() - 6.0)
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
            if static:
                shoulder_world = self._rotate_point(shoulder, pivot, theta)
                hand_world = QPointF(
                    shoulder_world.x() + side * 4.0,
                    shoulder_world.y() + 20.0,
                )
                control_world = QPointF(
                    (shoulder_world.x() + hand_world.x()) / 2.0 + side * 3.0,
                    shoulder_world.y() + 10.0,
                )
                hand = self._rotate_point(hand_world, pivot, -theta)
                control = self._rotate_point(control_world, pivot, -theta)
            elif cheering:
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

    def _draw_wound(self, painter: QPainter) -> None:
        if not self._alive or self._grudge_remaining <= 0.0:
            return

        alpha = min(1.0, self._grudge_remaining / 2.0)
        side = self._wound_side
        cx = BODY.center().x()

        painter.save()
        painter.setOpacity(alpha)

        painter.save()
        painter.translate(cx + side * 13.0, BODY.top() + 17.0)
        painter.rotate(side * 26.0)
        painter.setPen(QPen(QColor(255, 255, 255, 225), 1.2))
        painter.setBrush(QColor("#F2C98A"))
        painter.drawRoundedRect(QRectF(-13.0, -4.5, 26.0, 9.0), 4.0, 4.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#E2AE68"))
        painter.drawRoundedRect(QRectF(-5.5, -3.6, 11.0, 7.2), 2.0, 2.0)
        painter.setBrush(QColor(190, 140, 80, 190))
        for dot_x in (-9.0, -7.2, 7.2, 9.0):
            painter.drawEllipse(QPointF(dot_x, 0.0), 0.6, 0.6)
        painter.restore()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(160, 100, 170, int(alpha * 70)))
        painter.drawEllipse(QPointF(cx - side * 18.0, BODY.top() + 35.0), 4.2, 3.0)
        painter.restore()

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
        memory = self._app.memory_bytes / (1024.0 * 1024.0)
        return (
            f"{self._app.name}\n"
            f"内存 ≈ {memory:.1f} MB\n"
            f"CPU {self._app.cpu_percent:.1f}%\n"
            f"{count} 个进程\n"
            "双击切换到该 App"
        )

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
