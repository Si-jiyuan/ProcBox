from __future__ import annotations

import math
import random
from enum import Enum

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QGraphicsObject, QToolTip

from procbox import config
from procbox.core.models import AppInfo
from procbox.core.motion import Motion, random_velocity, step
from procbox.ui.bubble import SpeechBubble
from procbox.ui.effects import FRAME_FPS, Effect, EffectArt
from procbox.ui.face import Expression, draw_face, pick_expression

BODY = QRectF(config.BODY_X, config.BODY_Y, config.BODY_SIZE, config.BODY_SIZE)
LIMB_BLACK = QColor("#111111")
LIMB_OUTLINE = QColor("#FFFFFF")
DEAD_LIMB = QColor("#B8B8B8")
DEAD_OUTLINE = QColor("#EEEEEE")
GROAN_LINES = ["呃…", "啊…", "唔…", "好痛…", "咳…"]
PHYSICS_ROLL_RATE = 0.45
DRAG_ROPE_LENGTH = 42.0
DRAG_SPRING = 85.0
DRAG_DAMPING = 2.2
DRAG_MAX_SPEED = 1_300.0
DRAG_ROTATION_RESPONSE = 45.0


class LyingPose(Enum):
    PRONE = "prone"
    SUPINE = "supine"


class AppSprite(QGraphicsObject):
    """One app icon with Q-style limbs, a face and a tiny social life."""

    activated = Signal(str)
    drag_started = Signal(str)
    hovered = Signal(str)

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

        self._hovered = False
        self._dragging = False
        self._drag_pending = False
        self._drag_pending_pos = QPointF()
        self._drag_anchor = QPointF()
        self._drag_rest_dir = QPointF(0.0, 1.0)
        self._drag_vel_x = 0.0
        self._drag_vel_y = 0.0
        self._physics_active = False
        self._physics_vx = 0.0
        self._physics_vy = 0.0
        self._physics_angular = 0.0
        self._physics_spin = 0.0
        self._physics_energy = 0.0
        self._impact_timer = 0.0
        self._recovering = False
        self._getting_up = False
        self._recovery_timer = 0.0
        self._get_up_timer = 0.0
        self._landing_position: QPointF | None = None
        self._activity_effect: Effect | None = None
        self._activity_target: Effect | None = None
        self._activity_progress = 0.0
        self._activity_time = 0.0

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
    def is_dragging(self) -> bool:
        return self._dragging

    @property
    def is_physics_active(self) -> bool:
        return self._physics_active

    @property
    def is_recovering(self) -> bool:
        return self._recovering

    @property
    def landing_position(self) -> QPointF | None:
        return self._landing_position

    @property
    def physics_velocity(self) -> tuple[float, float]:
        return self._physics_vx, self._physics_vy

    @property
    def physics_speed(self) -> float:
        return math.hypot(self._physics_vx, self._physics_vy)

    @property
    def physics_energy(self) -> float:
        return self._physics_energy

    def set_physics_energy(self, energy: float) -> None:
        self._physics_energy = max(0.1, min(1.0, energy))

    @property
    def can_be_bumped(self) -> bool:
        return self._alive and not (
            self._knocked_down
            or self._chatting
            or self._fighting
            or self._fleeing
            or self._chasing
            or self._caring
            or self._dragging
            or self._recovering
            or self.is_activity_animating
        )

    def can_be_dragged(self) -> bool:
        return self._alive and not self._dragging

    @property
    def activity_effect(self) -> Effect | None:
        return self._activity_effect

    @property
    def is_activity_animating(self) -> bool:
        return self._activity_effect is not None

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
    def facing(self) -> float:
        return self._facing

    def set_facing(self, facing: float) -> None:
        self._facing = 1.0 if facing >= 0.0 else -1.0

    @property
    def center_scene(self) -> QPointF:
        return QPointF(
            self.pos().x() + BODY.center().x(),
            self.pos().y() + BODY.center().y(),
        )

    def boundingRect(self) -> QRectF:
        if self._physics_active or self._recovering:
            return QRectF(-24.0, -24.0, self._size + 48.0, self._size + 48.0)
        return QRectF(0.0, 0.0, self._size, self._size)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if not self._alive or self._knocked_down or self._dragging or self._physics_active:
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

        if self._impact_timer > 0.0:
            impact = min(1.0, self._impact_timer / 0.18)
            painter.translate(center)
            painter.scale(1.0 + 0.10 * impact, 1.0 - 0.10 * impact)
            painter.translate(-center)

        self._draw_shadow(painter)
        self._draw_limbs(painter)
        pixmap = self._color_pixmap if self._alive else (self._gray_pixmap or self._color_pixmap)
        painter.drawPixmap(BODY.topLeft(), pixmap)
        self._draw_face_cached(painter)
        self._draw_wound(painter)
        self._draw_activity_effect(painter)
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
        self._tick_activity_effect(dt)
        if self._knocked_down:
            self._tick_down(dt)
            return

        if self._recovering:
            self._tick_face(dt)
            self._impact_timer = max(0.0, self._impact_timer - dt)
            self.update()
            if self._getting_up:
                self._get_up_timer -= dt
                if self._get_up_timer <= 0.0:
                    self._getting_up = False
                    self.prepareGeometryChange()
                    self._recovering = False
                    self._recovery_timer = 0.0
                    self._expression = Expression.HAPPY
                    self._expression_timer = self._rng.uniform(2.0, 4.5)
                    self._wake_up()
                return

            self._recovery_timer -= dt
            if self._recovery_timer <= 0.0:
                self._getting_up = True
                self._get_up_timer = 0.42
                self._expression = Expression.HAPPY
                self._expression_timer = 99.0
                self._play_get_up_animation()
            return

        self._tick_face(dt)

        if self._dragging:
            self._tick_drag_rope(dt, width, height)
            self._impact_timer = max(0.0, self._impact_timer - dt)
            self._move_phase += dt * 4.0
            self.update()
            return

        if self._physics_active:
            self._impact_timer = max(0.0, self._impact_timer - dt)
            self._move_phase += dt * (4.0 + self.physics_speed / 25.0)
            self.update()
            return

        if self._fleeing or self._chasing:
            self._tick_run(dt, width, height)
            return

        if self._caring:
            self._move_phase += dt * 8.0
            return

        if self._spectating:
            if self._watch_target is not None:
                if self._hovered:
                    self.update()
                else:
                    self._tick_gather(dt, width, height)
            else:
                self.update()
            return

        if self._chatting or self._fighting:
            self.update()
            return

        if self._hovered:
            self.update()
            return

        if (
            self._activity_effect is not None
            and self._activity_progress > 0.15
            and not self._activity_busy()
        ):
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
        if self._physics_active:
            self.setZValue(1_000_000.0 + y + self._size)
        elif self._dragging:
            self.setZValue(2_000_000.0)
        else:
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
        self._clear_pointer_state()
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
        self._clear_pointer_state()
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

    def _play_get_up_animation(self) -> None:
        self._fall_anim.stop()
        self._fall_anim.setDuration(420)
        self._fall_anim.setStartValue(self.rotation())
        self._fall_anim.setEndValue(0.0)
        self._fall_anim.setEasingCurve(QEasingCurve.Type.OutBack)
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
        self._play_get_up_animation()
        self._wake_up()

    def begin_watch(self, focus: QPointF) -> None:
        if not self._alive or self._knocked_down:
            return
        self._clear_pointer_state()
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
        self._clear_pointer_state()
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
        self._clear_pointer_state()
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
        self._clear_pointer_state()
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
        self._clear_pointer_state()
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

    def hide_bubble(self) -> None:
        self._bubble.hide_now()

    def set_activity_effect(self, effect: Effect | None) -> None:
        if effect is not None and self._activity_busy():
            effect = None
        if effect == self._activity_target:
            return
        self._activity_target = effect
        if effect is not None:
            if self._rest_remaining > 0.0:
                facing = self.facing
                self._wake_up()
                self.set_facing(facing)
            self._activity_effect = effect
            self._activity_progress = 0.0
            self._activity_time = 0.0

    def _activity_busy(self) -> bool:
        return (
            not self._alive
            or self._knocked_down
            or self._dragging
            or self._physics_active
            or self._fighting
            or self._chatting
            or self._spectating
            or self._helping
            or self._fleeing
            or self._chasing
            or self._caring
            or self._recovering
        )

    def _tick_activity_effect(self, dt: float) -> None:
        if self._activity_busy():
            self._activity_target = None
        if self._activity_target is None:
            if self._activity_effect is not None:
                self._activity_progress = max(0.0, self._activity_progress - dt * 4.0)
                if self._activity_progress <= 0.0:
                    self._activity_effect = None
                    self._expression_timer = 0.0
            return
        self._activity_progress = min(1.0, self._activity_progress + dt * 4.0)
        self._activity_time += dt

    def cancel_fight(self) -> None:
        if not self._alive:
            return
        self._fighting = False
        self._bubble.hide_now()
        if not self._dragging:
            if self.is_grudging:
                self._expression = Expression.ANGRY
                self._expression_timer = self._grudge_remaining
            else:
                self._expression = Expression.HAPPY
                self._expression_timer = self._rng.uniform(2.0, 4.5)
            self._wake_up()
        self.update()

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
        self._clear_pointer_state()
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

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._alive and not self._dragging:
            self._drag_pending = True
            self._drag_pending_pos = QPointF(event.scenePos())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pending and not self._dragging:
            dx = event.scenePos().x() - self._drag_pending_pos.x()
            dy = event.scenePos().y() - self._drag_pending_pos.y()
            if dx * dx + dy * dy >= 16.0 and self.begin_drag(self._drag_pending_pos):
                self.drag_to(event.scenePos())
            event.accept()
            return
        if self._dragging:
            self.drag_to(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self.release_drag(event.scenePos())
        elif self._drag_pending:
            self._drag_pending = False
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        self._drag_pending = False
        if self._dragging:
            self.cancel_drag()
        if self._alive:
            self.activated.emit(self._app.app_id)
        event.accept()

    def hoverEnterEvent(self, event) -> None:
        if self._alive and not self._dragging:
            self._hovered = True
            self.hovered.emit(self._app.app_id)
            self.setToolTip(self._tooltip())
            scene = self.scene()
            view = scene.views()[0] if scene is not None and scene.views() else None
            QToolTip.showText(
                QCursor.pos(),
                self._tooltip(),
                view,
                QRect(),
                10_000,
            )
            if not self._knocked_down and not self._physics_active:
                self._animate_scale(1.08, 130)
        event.accept()

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        QToolTip.hideText()
        if not self._dragging:
            self._animate_scale(1.0, 160)
        event.accept()

    def begin_drag(self, scene_pos: QPointF) -> bool:
        if self._dragging or not self.can_be_dragged():
            return False
        self._clear_pointer_state()
        self._drag_pending = False
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
        self._down_groan_timer = 0.0
        self._rest_remaining = 0.0
        self._dragging = True
        self._hovered = False
        self._drag_anchor = QPointF(scene_pos)
        self._drag_vel_x = 0.0
        self._drag_vel_y = 0.0
        center = self.center_scene
        dx = center.x() - scene_pos.x()
        dy = center.y() - scene_pos.y()
        length = math.hypot(dx, dy)
        if length < 1.0:
            self._drag_rest_dir = QPointF(0.0, 1.0)
        else:
            self._drag_rest_dir = QPointF(dx / length, dy / length)
        self._expression = Expression.SURPRISED
        self._expression_timer = 99.0
        self._bubble.hide_now()
        self._scale_anim.stop()
        self.setScale(1.08)
        self.setZValue(2_000_000.0)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        QToolTip.hideText()
        self.update()
        self.drag_started.emit(self._app.app_id)
        return True

    def drag_to(self, scene_pos: QPointF) -> None:
        if not self._dragging:
            return
        self._drag_anchor = QPointF(scene_pos)

    def _tick_drag_rope(self, dt: float, width: float, height: float) -> None:
        center = self.center_scene
        dx = center.x() - self._drag_anchor.x()
        dy = center.y() - self._drag_anchor.y()
        distance = math.hypot(dx, dy)
        if distance < 0.01:
            ux = self._drag_rest_dir.x()
            uy = self._drag_rest_dir.y()
        else:
            ux = dx / distance
            uy = dy / distance

        stretch = distance - DRAG_ROPE_LENGTH
        acceleration = -DRAG_SPRING * stretch
        vx = self._drag_vel_x + ux * acceleration * dt
        vy = self._drag_vel_y + uy * acceleration * dt

        damping = math.exp(-DRAG_DAMPING * dt)
        vx *= damping
        vy *= damping
        speed = math.hypot(vx, vy)
        if speed > DRAG_MAX_SPEED:
            factor = DRAG_MAX_SPEED / speed
            vx *= factor
            vy *= factor

        self._drag_vel_x = vx
        self._drag_vel_y = vy
        max_x = max(0.0, width - self._size)
        max_y = max(0.0, height - self._size)
        x = min(max(center.x() + vx * dt - BODY.center().x(), 0.0), max_x)
        y = min(max(center.y() + vy * dt - BODY.center().y(), 0.0), max_y)
        self._motion = Motion(x, y, vx, vy)
        self.setPos(x, y)
        self.setZValue(2_000_000.0)

        toward_x = self._drag_anchor.x() - (x + BODY.center().x())
        toward_y = self._drag_anchor.y() - (y + BODY.center().y())
        if abs(toward_x) + abs(toward_y) > 0.01:
            target = math.degrees(math.atan2(toward_y, toward_x)) + 90.0
            current = self.rotation()
            delta = (target - current + 180.0) % 360.0 - 180.0
            blend = 1.0 - math.exp(-DRAG_ROTATION_RESPONSE * dt)
            self.setRotation((current + delta * blend + 180.0) % 360.0 - 180.0)

    def release_drag(self, scene_pos: QPointF) -> None:
        if not self._dragging:
            return
        self._drag_anchor = QPointF(scene_pos)
        self._dragging = False
        self.setScale(1.0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False
        QToolTip.hideText()

        vx = self._drag_vel_x * 1.15
        vy = self._drag_vel_y * 1.15
        speed = math.hypot(vx, vy)
        if speed > 1_700.0:
            factor = 1_700.0 / speed
            vx *= factor
            vy *= factor
            speed = 1_700.0

        self._drag_vel_x = 0.0
        self._drag_vel_y = 0.0
        if speed >= 80.0:
            self.begin_physics(
                vx,
                vy,
                spin=self.roll_angular(vx, vy),
                initial_rotation=self.rotation(),
            )
        else:
            self._expression = Expression.HAPPY
            self._expression_timer = self._rng.uniform(2.0, 4.5)
            self._wake_up()
            self._settle_drag_rotation()

    def _clear_pointer_state(self) -> None:
        if self._physics_active or self._recovering:
            self.prepareGeometryChange()
        self._dragging = False
        self._drag_vel_x = 0.0
        self._drag_vel_y = 0.0
        self._physics_active = False
        self._physics_vx = 0.0
        self._physics_vy = 0.0
        self._physics_angular = 0.0
        self._physics_spin = 0.0
        self._physics_energy = 0.0
        self._impact_timer = 0.0
        self._hovered = False
        self._recovering = False
        self._getting_up = False
        self._recovery_timer = 0.0
        self._get_up_timer = 0.0
        self._landing_position = None
        self._fall_anim.stop()
        self.setRotation(0.0)
        self._scale_anim.stop()
        self.setScale(1.0)

    def cancel_drag(self) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._drag_vel_x = 0.0
        self._drag_vel_y = 0.0
        self.setScale(1.0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False
        QToolTip.hideText()
        self._expression = Expression.HAPPY
        self._expression_timer = self._rng.uniform(2.0, 4.5)
        self._wake_up()
        self._settle_drag_rotation()

    def _settle_drag_rotation(self) -> None:
        if abs(self.rotation()) < 0.1:
            self.setRotation(0.0)
            return
        self._fall_anim.stop()
        self._fall_anim.setDuration(240)
        self._fall_anim.setStartValue(self.rotation())
        self._fall_anim.setEndValue(0.0)
        self._fall_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fall_anim.start()

    def begin_physics(
        self,
        vx: float,
        vy: float,
        spin: float = 0.0,
        energy: float = 1.0,
        initial_rotation: float | None = None,
    ) -> None:
        if not self._alive:
            return
        if not (self._physics_active or self._recovering):
            self.prepareGeometryChange()
        self._fall_anim.stop()
        self._physics_active = True
        self._dragging = False
        self._spectating = False
        self._helping = False
        self._watch_target = None
        self._watch_focus = None
        self._recovering = False
        self._getting_up = False
        self._recovery_timer = 0.0
        self._get_up_timer = 0.0
        self._landing_position = None
        self.set_physics_velocity(vx, vy)
        self.set_physics_energy(energy)
        self._physics_angular = spin
        if initial_rotation is None:
            self._physics_spin = 0.0
            self.setRotation(0.0)
        else:
            self._physics_spin = (initial_rotation + 180.0) % 360.0 - 180.0
            self.setRotation(self._physics_spin)
        self._impact_timer = 0.16
        self._rest_remaining = 0.0
        self._expression = Expression.SCREAM
        self._expression_timer = 99.0
        self._bubble.hide_now()
        self.setScale(1.0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setZValue(1_000_000.0 + self.pos().y() + self._size)
        self.update()

    def bump_physics(
        self,
        vx: float,
        vy: float,
        spin: float = 0.0,
        energy: float = 0.5,
    ) -> None:
        if not self.can_be_bumped:
            return
        if not self._physics_active:
            self.begin_physics(vx, vy, spin, energy=energy)
            return
        self.set_physics_velocity(vx, vy)
        self.set_physics_energy(energy)
        self._physics_angular = spin
        self._impact_timer = 0.16
        self._expression = Expression.SCREAM
        self._expression_timer = 99.0
        self.setZValue(1_000_000.0 + self.pos().y() + self._size)
        self.update()

    def set_physics_velocity(self, vx: float, vy: float) -> None:
        speed = math.hypot(vx, vy)
        if speed > 1_800.0:
            factor = 1_800.0 / speed
            vx *= factor
            vy *= factor
        self._physics_vx = vx
        self._physics_vy = vy

    def scale_physics_velocity(self, factor: float) -> None:
        self._physics_vx *= factor
        self._physics_vy *= factor

    def set_physics_angular(self, angular: float) -> None:
        self._physics_angular = angular

    @staticmethod
    def roll_angular(vx: float, vy: float) -> float:
        """Clockwise for rightward motion, counter-clockwise for leftward."""
        speed = math.hypot(vx, vy)
        if speed == 0.0:
            return 0.0
        sign = 1.0 if vx >= 0.0 else -1.0
        return sign * speed * PHYSICS_ROLL_RATE

    def integrate_physics(self, dt: float, width: float, height: float) -> None:
        if not self._physics_active:
            return
        vx = self._physics_vx
        vy = self._physics_vy
        x = self.pos().x() + vx * dt
        y = self.pos().y() + vy * dt
        max_x = max(0.0, width - self._size)
        max_y = max(0.0, height - self._size)
        bounced = False

        if x < 0.0:
            x = 0.0
            vx = abs(vx) * 0.72
            bounced = True
        elif x > max_x:
            x = max_x
            vx = -abs(vx) * 0.72
            bounced = True
        if y < 0.0:
            y = 0.0
            vy = abs(vy) * 0.72
            bounced = True
        elif y > max_y:
            y = max_y
            vy = -abs(vy) * 0.72
            bounced = True

        if bounced:
            self._impact_timer = 0.16
            self._physics_angular = self.roll_angular(vx, vy)
        self._physics_vx = vx
        self._physics_vy = vy
        self._motion = Motion(x, y, vx, vy)
        self.setPos(x, y)
        self.setZValue(1_000_000.0 + y + self._size)
        self._physics_spin = (self._physics_spin + self._physics_angular * dt) % 360.0
        self.setRotation(self._physics_spin)
        self._move_phase += dt * (3.5 + math.hypot(vx, vy) / 22.0)

    def apply_physics_friction(self, dt: float) -> None:
        if not self._physics_active:
            return
        speed = self.physics_speed
        damping = math.exp(-(1.7 if speed > 160.0 else 3.0) * dt)
        self._physics_vx *= damping
        self._physics_vy *= damping
        self._physics_angular *= math.exp(-2.0 * dt)
        if math.hypot(self._physics_vx, self._physics_vy) < 55.0:
            self.stop_physics()

    def shift_physics_center(
        self,
        dx: float,
        dy: float,
        width: float,
        height: float,
    ) -> None:
        max_x = max(0.0, width - self._size)
        max_y = max(0.0, height - self._size)
        x = min(max(self.pos().x() + dx, 0.0), max_x)
        y = min(max(self.pos().y() + dy, 0.0), max_y)
        self._motion = Motion(x, y, self._physics_vx, self._physics_vy)
        self.setPos(x, y)
        self.setZValue(1_000_000.0 + y + self._size)

    def add_physics_impact(self) -> None:
        self._impact_timer = 0.18

    def stop_physics(self) -> None:
        if not self._physics_active:
            return
        self._physics_active = False
        self._physics_vx = 0.0
        self._physics_vy = 0.0
        self._physics_angular = 0.0
        self._physics_spin = 0.0
        self._physics_energy = 0.0
        self._impact_timer = 0.0
        self.setScale(1.0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if not self._alive:
            self.setRotation(0.0)
            return

        self._landing_position = QPointF(self.pos())
        self._motion = Motion(self.pos().x(), self.pos().y(), 0.0, 0.0)
        self._recovering = True
        self._getting_up = False
        self._recovery_timer = self._rng.uniform(0.45, 0.9)
        self._get_up_timer = 0.0
        self._expression = Expression.SURPRISED
        self._expression_timer = 99.0
        self.setZValue(self.pos().y() + self._size)

        rotation = (self.rotation() + 180.0) % 360.0 - 180.0
        self.setRotation(rotation)
        head_x = math.sin(math.radians(rotation))
        self._lying_pose = LyingPose.PRONE if head_x >= 0.0 else LyingPose.SUPINE
        if self._lying_pose is LyingPose.PRONE:
            target = self._rng.uniform(80.0, 98.0)
        else:
            target = -self._rng.uniform(80.0, 98.0)
        self._fall_anim.stop()
        self._fall_anim.setDuration(260)
        self._fall_anim.setStartValue(self.rotation())
        self._fall_anim.setEndValue(target)
        self._fall_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fall_anim.start()
        self.update()

    def _draw_activity_effect(self, painter: QPainter) -> None:
        effect = self._activity_effect
        if effect is None or self._activity_progress <= 0.0 or self._activity_busy():
            return
        frame = EffectArt.frame(effect, int(self._activity_time * FRAME_FPS))
        center = BODY.center()
        painter.save()
        painter.setOpacity(self._activity_progress)
        painter.translate(center)
        zoom = 0.88 + 0.12 * self._activity_progress
        painter.scale(zoom, zoom)
        painter.translate(-center)
        mirror = (effect is Effect.NETWORK and self._facing > 0.0) or (
            effect is Effect.AUDIO and self._facing < 0.0
        )
        if mirror:
            painter.translate(self._size, 0.0)
            painter.scale(-1.0, 1.0)
        painter.drawPixmap(0.0, 0.0, frame)
        painter.restore()

    def _face_key(self) -> tuple:
        return (
            self._expression,
            self._blink_remaining > 0.0 or self._knocked_down or self._physics_active,
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
                self._blink_remaining > 0.0 or self._knocked_down or self._physics_active,
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

        if self._physics_active:
            self._expression = Expression.SCREAM
            self._expression_timer = 99.0
        elif self._recovering:
            self._expression = Expression.SLEEPY
            self._expression_timer = 99.0
        elif self._fighting or self._helping or self._fleeing or self._chasing:
            self._expression = Expression.ANGRY
            self._expression_timer = 99.0
        elif (
            self._activity_effect is not None
            and self._activity_progress > 0.05
            and not self._activity_busy()
        ):
            if self._activity_effect is Effect.AUDIO:
                self._expression = Expression.SHOUT
            elif self._activity_effect is Effect.NETWORK:
                self._expression = Expression.HAPPY
            else:
                self._expression = Expression.FOCUSED
            self._expression_timer = 99.0
        elif self._grudge_remaining > 0.0:
            self._grudge_remaining = max(0.0, self._grudge_remaining - dt)
            if self._grudge_remaining > 0.0:
                if (
                    not self._chatting
                    and not self._spectating
                    and not self._caring
                    and not self._recovering
                ):
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
        self._motion = Motion(self.pos().x(), self.pos().y(), vx, vy)
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

    def _draw_dragging_limbs(self, painter: QPainter) -> None:
        limb_color = LIMB_BLACK
        outline_color = LIMB_OUTLINE
        cx = BODY.center().x()

        for side in (-1, 1):
            phase = self._anim_time * 3.5 + side * 0.8
            hip = QPointF(cx + side * 9.5, BODY.bottom() - 6.0)
            ankle = QPointF(
                cx + side * 10.0 + math.sin(phase) * 6.0,
                82.0 + math.cos(phase) * 1.5,
            )
            toe = QPointF(ankle.x() + side * 6.0, ankle.y())
            leg = QPainterPath(hip)
            leg.lineTo(ankle)
            leg.lineTo(toe)
            self._stroke_path(painter, leg, outline_color, 7.0)
            self._stroke_path(painter, leg, limb_color, 4.4)

        for side in (-1, 1):
            phase = self._anim_time * 4.2 + side * 1.1
            shoulder = QPointF(cx + side * 20.0, BODY.top() + 36.0)
            hand = QPointF(
                cx + side * 24.0 + math.sin(phase) * 7.0,
                76.0 + math.cos(phase) * 2.0,
            )
            control = QPointF(cx + side * 22.0, 58.0)
            arm = QPainterPath(shoulder)
            arm.quadTo(control, hand)
            self._stroke_path(painter, arm, outline_color, 6.4)
            self._stroke_path(painter, arm, limb_color, 4.0)
            painter.setPen(QPen(outline_color, 1.5))
            painter.setBrush(limb_color)
            painter.drawEllipse(hand, 3.6, 3.6)

    def _draw_ragdoll_limbs(self, painter: QPainter) -> None:
        limb_color = LIMB_BLACK
        outline_color = LIMB_OUTLINE
        cx = BODY.center().x()

        intensity = min(1.0, max(0.12, self.physics_speed / 450.0))
        for side in (-1, 1):
            wobble = math.sin(self._anim_time * 10.0 + side * 1.7) * 7.0 * intensity
            hip = QPointF(cx + side * 9.5, BODY.bottom() - 6.0)
            ankle = QPointF(
                cx + side * 19.0 + wobble * 0.5,
                78.0 + wobble * 0.4,
            )
            toe = QPointF(ankle.x() + side * 8.0, ankle.y())
            leg = QPainterPath(hip)
            leg.lineTo(ankle)
            leg.lineTo(toe)
            self._stroke_path(painter, leg, outline_color, 7.0)
            self._stroke_path(painter, leg, limb_color, 4.4)

        for side in (-1, 1):
            wobble = math.sin(self._anim_time * 9.0 + side) * 8.0 * intensity
            shoulder = QPointF(cx + side * 20.0, BODY.top() + 36.0)
            hand = QPointF(
                cx + side * 36.0,
                BODY.top() + 22.0 + wobble,
            )
            control = QPointF(cx + side * 30.0, BODY.top() + 26.0)
            arm = QPainterPath(shoulder)
            arm.quadTo(control, hand)
            self._stroke_path(painter, arm, outline_color, 6.4)
            self._stroke_path(painter, arm, limb_color, 4.0)
            painter.setPen(QPen(outline_color, 1.5))
            painter.setBrush(limb_color)
            painter.drawEllipse(hand, 3.6, 3.6)

    def _draw_limbs(self, painter: QPainter) -> None:
        if self._dragging:
            self._draw_dragging_limbs(painter)
            return
        if self._physics_active:
            self._draw_ragdoll_limbs(painter)
            return

        dead = not self._alive
        limb_color = DEAD_LIMB if dead else LIMB_BLACK
        outline_color = DEAD_OUTLINE if dead else LIMB_OUTLINE
        cx = BODY.center().x()
        static = dead or self._knocked_down or self._recovering
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

        arm_opacity = 1.0
        if (
            self._activity_effect is not None
            and self._activity_progress > 0.0
            and not self._activity_busy()
        ):
            arm_opacity = max(0.0, 1.0 - self._activity_progress)
        painter.save()
        painter.setOpacity(arm_opacity)
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
        painter.restore()

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
