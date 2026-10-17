from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPointF, QRectF, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsObject, QGraphicsScene
from shiboken6 import isValid

from procbox.core.relationships import RelationshipBook

if TYPE_CHECKING:
    from procbox.ui.sprite import AppSprite

FIGHT_LINES_A = ["你撞我？", "哎哟！", "看着点路！", "干嘛撞我！"]
FIGHT_LINES_B = ["来啊！", "谁怕谁！", "哼！", "是你撞我！"]
SPECTATOR_LINES = [
    "我押 {a} 赢！",
    "{b} 加油！",
    "{a} 看起来更厉害！",
    "这一拳好疼！",
    "{a} 别输啊！",
    "{b} 快还手！",
    "我赌 {a} 会赢！",
    "{a} 和 {b} 又打起来啦",
    "好精彩！{a} 冲呀！",
    "你们别打了！……继续",
]
BAD_LINES = [
    "{name} 撞人都不道歉！",
    "{name} 的图标一点也不可爱！",
    "{name} 整天就知道摸鱼！",
    "{name} 走路都不看路！",
    "{name} 刚才根本就没用力！",
    "{name} 是个大笨蛋！",
    "{name} 的技术真差！",
    "{name} 再撞我试试！",
    "{name} 就是个小气鬼！",
]
HELPER_LINES = [
    "{opponent} 别怕，我来帮你！",
    "一起上，{target}！",
    "{target} 又欺负人！",
    "这次你跑不掉了，{target}！",
]
THREAT_LINES = [
    "算你跑得快，{name}！",
    "下次别让我逮到你，{name}！",
    "{name} 有种别跑！",
    "哼，先放过 {name}！",
]
COLLISION_X = 58.0
COLLISION_Y = 56.0
PAIR_COOLDOWN = 30.0
GLOBAL_COOLDOWN = 20.0
JOIN_RADIUS = 300.0
JOIN_CHANCE = 0.6
CHASE_SECONDS = 4.0
CHASE_HEAD_START = 0.9
MIN_FIGHT_SECONDS = 10.0
MAX_FIGHT_SECONDS = 60.0
KNOCKDOWN_CHANCE = 0.4
AVOID_RADIUS = 175.0


def _spark_path(size: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(0.0, -size)
    path.lineTo(size * 0.24, -size * 0.24)
    path.lineTo(size, 0.0)
    path.lineTo(size * 0.24, size * 0.24)
    path.lineTo(0.0, size)
    path.lineTo(-size * 0.24, size * 0.24)
    path.lineTo(-size, 0.0)
    path.lineTo(-size * 0.24, -size * 0.24)
    path.closeSubpath()
    return path


class FightCloud(QGraphicsObject):
    """A cartoon dust cloud and action sparks shown between two fighters."""

    dismissed = Signal()

    def __init__(self, center: QPointF, duration_ms: int) -> None:
        super().__init__()
        self.setPos(center)
        self.setZValue(900_000.0)
        self._progress = 0.0
        self._duration = max(0.5, duration_ms / 1_000.0)
        self._disposed = False
        self._dust = [
            (-20.0, 5.0, 22.0),
            (-4.0, -6.0, 26.0),
            (16.0, 3.0, 21.0),
            (-9.0, 17.0, 18.0),
            (12.0, 17.0, 16.0),
            (0.0, 4.0, 24.0),
        ]
        self._sparks = [(-28.0, -16.0, 11.0), (24.0, -20.0, 9.0), (2.0, 25.0, 8.0)]

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(duration_ms)
        self._anim.valueChanged.connect(self._set_progress)
        self._anim.finished.connect(self._dispose)
        self._anim.start()

    def boundingRect(self) -> QRectF:
        return QRectF(-58.0, -48.0, 116.0, 96.0)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        elapsed = self._progress * self._duration
        fade_in = min(1.0, elapsed / 0.25)
        fade_out = min(1.0, (self._duration - elapsed) / 0.4)
        fade = min(fade_in, fade_out)
        if fade <= 0.0:
            return

        pulse = 1.0 + math.sin(elapsed * 8.0) * 0.035
        painter.save()
        painter.setOpacity(max(0.0, fade))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        for index, (dx, dy, radius) in enumerate(self._dust):
            jitter_x = math.sin(elapsed * 9.0 + index * 1.7) * 2.4
            jitter_y = math.cos(elapsed * 7.6 + index * 2.1) * 1.8
            painter.setPen(QPen(QColor(105, 105, 105, 190), 1.3))
            painter.setBrush(
                QColor(252, 252, 248, 235) if index % 2 == 0 else QColor(225, 225, 223, 235)
            )
            painter.drawEllipse(
                QPointF(dx + jitter_x, dy + jitter_y),
                radius * pulse,
                radius * 0.82 * pulse,
            )

        for index, (dx, dy, size) in enumerate(self._sparks):
            painter.save()
            painter.translate(dx, dy + math.sin(elapsed * 5.0 + index) * 2.0)
            painter.rotate(elapsed * 120.0 * (1.0 if index % 2 == 0 else -1.0) + index * 35.0)
            painter.setPen(QPen(QColor(160, 108, 18), 1.2))
            painter.setBrush(QColor(255, 214, 88))
            painter.drawPath(_spark_path(size))
            painter.restore()

        painter.setPen(QPen(QColor(255, 255, 255, 190), 2.0))
        for angle in (0.4, 1.5, 2.6, 3.7, 4.9, 5.8):
            wobble = math.sin(elapsed * 6.5 + angle) * 0.12
            inner = QPointF(math.cos(angle + wobble) * 32.0, math.sin(angle + wobble) * 24.0)
            outer = QPointF(math.cos(angle + wobble) * 42.0, math.sin(angle + wobble) * 33.0)
            painter.drawLine(inner, outer)

        painter.restore()

    def _set_progress(self, value) -> None:
        self._progress = float(value)
        self.update()

    def dismiss(self) -> None:
        if not isValid(self) or self._disposed:
            return
        self._disposed = True
        if isValid(self._anim):
            self._anim.stop()
        scene = self.scene()
        if scene is not None:
            scene.removeItem(self)
        self.dismissed.emit()
        self.deleteLater()

    def _dispose(self) -> None:
        self.dismiss()


class FightDirector(QObject):
    """Turns occasional collisions into long, purely cosmetic brawls."""

    def __init__(
        self,
        scene: QGraphicsScene,
        sprites: dict[str, AppSprite],
        rng: random.Random,
        parent=None,
        relationships: RelationshipBook | None = None,
    ) -> None:
        super().__init__(parent)
        self._scene = scene
        self._sprites = sprites
        self._rng = rng
        self._relationships = relationships or RelationshipBook()
        self._active: tuple[AppSprite, AppSprite] | None = None
        self._token = 0
        self._overlapping: set[tuple[int, int]] = set()
        self._cooldowns: dict[tuple[int, int], float] = {}
        self._global_ready = 0.0
        self._spectators: list[AppSprite] = []
        self._spectator_phase = 0.0
        self._join_attempted: set[str] = set()
        self._cloud: FightCloud | None = None
        self._midpoint: QPointF | None = None
        self._notorious_fighter: AppSprite | None = None
        self._notorious_opponent: AppSprite | None = None
        self._notorious_helpers: list[AppSprite] = []
        self._chase_target: AppSprite | None = None
        self._chasers: list[AppSprite] = []
        self._chase_deadline = 0.0
        self._chase_grace_until = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._check_collisions)
        self._timer.start()

        self._crowd_timer = QTimer(self)
        self._crowd_timer.setSingleShot(True)
        self._crowd_timer.timeout.connect(self._crowd_talk)

        self._join_timer = QTimer(self)
        self._join_timer.setSingleShot(True)
        self._join_timer.timeout.connect(self._maybe_join)

        self._chase_timer = QTimer(self)
        self._chase_timer.setInterval(100)
        self._chase_timer.timeout.connect(self._check_chase)

    @property
    def avoid_zone(self) -> tuple[QPointF, float] | None:
        if self._active is None or self._midpoint is None:
            return None
        return self._midpoint, AVOID_RADIUS

    def stop(self) -> None:
        self._timer.stop()
        self._crowd_timer.stop()
        self._join_timer.stop()
        self._chase_timer.stop()
        self._abort_chase()
        self._token += 1
        if self._active is not None:
            for sprite in self._active:
                if sprite.is_alive:
                    sprite.end_fight()
            self._active = None
        self._midpoint = None
        self._end_spectators()
        self._clear_cloud()
        self._notorious_fighter = None
        self._notorious_opponent = None
        self._notorious_helpers = []

    def _check_collisions(self) -> None:
        if self._chase_target is not None:
            return
        now = time.monotonic()
        if self._active is not None:
            if not all(sprite.is_alive for sprite in self._active):
                self._finish(self._token)
            return

        alive = [
            sprite
            for sprite in self._sprites.values()
            if sprite.is_alive
            and not sprite.is_chatting
            and not sprite.is_fighting
            and not sprite.is_spectating
            and not sprite.is_helping
            and not sprite.is_fleeing
            and not sprite.is_chasing
            and not sprite.is_caring
            and not sprite.is_knocked_down
        ]
        current: set[tuple[int, int]] = set()
        candidates: list[tuple[AppSprite, AppSprite, tuple[int, int]]] = []

        for index, first in enumerate(alive):
            first_center = first.center_scene
            for second in alive[index + 1 :]:
                second_center = second.center_scene
                if (
                    abs(first_center.x() - second_center.x()) >= COLLISION_X
                    or abs(first_center.y() - second_center.y()) >= COLLISION_Y
                ):
                    continue

                key = (min(id(first), id(second)), max(id(first), id(second)))
                current.add(key)
                if key in self._overlapping:
                    continue
                if first.is_saying or second.is_saying:
                    continue
                if now - self._cooldowns.get(key, 0.0) <= PAIR_COOLDOWN:
                    continue
                if now < self._global_ready:
                    continue
                chance = 0.35 * self._relationships.fight_multiplier(
                    first.app.app_id,
                    second.app.app_id,
                    now,
                )
                if chance <= 0.0 or self._rng.random() > min(1.0, chance):
                    continue
                candidates.append((first, second, key))

        self._overlapping = current
        if not candidates:
            return

        first, second, key = self._rng.choice(candidates)
        self._start_fight(first, second, key, now)

    def _start_fight(
        self,
        first: AppSprite,
        second: AppSprite,
        key: tuple[int, int],
        now: float,
    ) -> None:
        self._token += 1
        token = self._token
        fight_seconds = self._rng.uniform(MIN_FIGHT_SECONDS, MAX_FIGHT_SECONDS)
        self._active = (first, second)
        self._midpoint = None
        self._cooldowns[key] = now + PAIR_COOLDOWN

        first_center = first.center_scene
        second_center = second.center_scene
        dx = second_center.x() - first_center.x()
        dy = second_center.y() - first_center.y()
        distance = math.hypot(dx, dy)
        if distance < 1.0:
            angle = self._rng.uniform(0.0, math.tau)
            ux, uy = math.cos(angle), math.sin(angle)
        else:
            ux, uy = dx / distance, dy / distance

        midpoint = QPointF(
            (first_center.x() + second_center.x()) / 2.0,
            (first_center.y() + second_center.y()) / 2.0,
        )
        self._midpoint = midpoint
        self._spectator_phase = self._rng.uniform(0.0, math.tau)
        self._join_attempted.clear()
        self._notorious_helpers = []
        self._notorious_fighter = None
        self._notorious_opponent = None

        first_partners = self._relationships.fight_partners(first.app.app_id)
        second_partners = self._relationships.fight_partners(second.app.app_id)
        notorious_candidates = []
        if len(first_partners) >= 3:
            notorious_candidates.append((len(first_partners), first, second))
        if len(second_partners) >= 3:
            notorious_candidates.append((len(second_partners), second, first))
        if notorious_candidates:
            _, notorious, opponent = max(notorious_candidates, key=lambda item: item[0])
            self._notorious_fighter = notorious
            self._notorious_opponent = opponent

        half_gap = 39.0
        first.move_center_to(QPointF(midpoint.x() - ux * half_gap, midpoint.y() - uy * half_gap))
        second.move_center_to(QPointF(midpoint.x() + ux * half_gap, midpoint.y() + uy * half_gap))

        rect = self._scene.sceneRect()
        first.constrain(rect.width(), rect.height())
        second.constrain(rect.width(), rect.height())

        first.begin_fight(second.center_scene)
        second.begin_fight(first.center_scene)
        self._gather_spectators(first, second, midpoint)
        self._clear_cloud()
        cloud = FightCloud(midpoint, int(fight_seconds * 1_000) + 300)
        cloud.dismissed.connect(lambda: self._cloud_dismissed(cloud))
        self._cloud = cloud
        self._scene.addItem(cloud)

        QTimer.singleShot(
            320,
            lambda: self._taunt(token, first, self._rng.choice(FIGHT_LINES_A)),
        )
        QTimer.singleShot(
            880,
            lambda: self._taunt(token, second, self._rng.choice(FIGHT_LINES_B)),
        )
        self._crowd_timer.start(self._rng.randint(1_500, 3_000))
        self._join_timer.start(self._rng.randint(1_200, 2_500))
        QTimer.singleShot(int(fight_seconds * 1_000), lambda: self._finish(token))

    def _clear_cloud(self) -> None:
        cloud = self._cloud
        self._cloud = None
        if cloud is not None:
            cloud.dismiss()

    def _cloud_dismissed(self, cloud: FightCloud) -> None:
        if self._cloud is cloud:
            self._cloud = None

    def _gather_spectators(
        self,
        first: AppSprite,
        second: AppSprite,
        midpoint: QPointF,
    ) -> None:
        nearby: list[tuple[float, AppSprite]] = []
        for sprite in self._sprites.values():
            if sprite is first or sprite is second:
                continue
            if not sprite.is_alive or sprite.is_chatting or sprite.is_fighting:
                continue
            if sprite.is_spectating or sprite.is_helping:
                continue
            if sprite.is_fleeing or sprite.is_chasing or sprite.is_caring:
                continue
            if sprite.is_knocked_down:
                continue
            center = sprite.center_scene
            distance = math.hypot(center.x() - midpoint.x(), center.y() - midpoint.y())
            if distance <= 340.0:
                nearby.append((distance, sprite))

        nearby.sort(key=lambda item: item[0])
        if not nearby:
            return

        for _, sprite in nearby:
            sprite.begin_watch(midpoint)
            self._spectators.append(sprite)
        self._promote_helpers()
        self._layout_spectators()

    def _maybe_join(self) -> None:
        if self._active is None or self._midpoint is None:
            return
        first, second = self._active
        midpoint = self._midpoint
        added = False

        for sprite in self._sprites.values():
            if sprite is first or sprite is second:
                continue
            if not sprite.is_alive:
                continue
            if sprite.is_chatting or sprite.is_fighting or sprite.is_spectating:
                continue
            if sprite.is_helping or sprite.is_fleeing or sprite.is_chasing:
                continue
            if sprite.is_caring or sprite.is_knocked_down:
                continue
            app_id = sprite.app.app_id
            if app_id in self._join_attempted:
                continue
            center = sprite.center_scene
            distance = math.hypot(center.x() - midpoint.x(), center.y() - midpoint.y())
            if distance > JOIN_RADIUS:
                continue
            self._join_attempted.add(app_id)
            if self._rng.random() >= JOIN_CHANCE:
                continue
            sprite.begin_watch(midpoint)
            self._spectators.append(sprite)
            added = True

        if added:
            self._promote_helpers()
            self._layout_spectators()
        self._join_timer.start(self._rng.randint(1_500, 3_000))

    def _promote_helpers(self) -> None:
        notorious = self._notorious_fighter
        if notorious is None or self._midpoint is None:
            return
        partners = self._relationships.fight_partners(notorious.app.app_id)
        for sprite in self._spectators:
            if sprite in self._notorious_helpers:
                continue
            if not sprite.is_alive or not sprite.is_spectating:
                continue
            if sprite.app.app_id in partners:
                sprite.begin_help(self._midpoint)
                self._notorious_helpers.append(sprite)

    def _layout_spectators(self) -> None:
        if not self._spectators or self._midpoint is None:
            return
        rect = self._scene.sceneRect()
        remaining = list(self._spectators)
        groups: list[list[AppSprite]] = []
        capacity = 6
        while remaining:
            groups.append(remaining[:capacity])
            remaining = remaining[capacity:]
            capacity += 2

        for ring, group in enumerate(groups):
            radius_x = 135.0 + ring * 90.0
            radius_y = 102.0 + ring * 68.0
            for index, sprite in enumerate(group):
                angle = self._spectator_phase + ring * 0.35 + index * math.tau / len(group)
                target = QPointF(
                    self._midpoint.x() + math.cos(angle) * radius_x,
                    self._midpoint.y() + math.sin(angle) * radius_y,
                )
                sprite.set_watch_target(target, rect.width(), rect.height())

    def _end_spectators(self) -> None:
        for sprite in self._spectators:
            if sprite.is_alive:
                sprite.end_watch()
        self._spectators = []

    def _crowd_talk(self) -> None:
        if self._active is None:
            return
        first, second = self._active
        alive = [sprite for sprite in self._spectators if sprite.is_alive and sprite.is_spectating]
        if not alive:
            return

        helpers = [
            sprite for sprite in self._notorious_helpers if sprite.is_alive and sprite.is_spectating
        ]
        notorious = self._notorious_fighter
        opponent = self._notorious_opponent
        if helpers and notorious is not None and opponent is not None and self._rng.random() < 0.75:
            quiet = [sprite for sprite in helpers if not sprite.is_saying]
            speaker = self._rng.choice(quiet or helpers)
            line = self._rng.choice(HELPER_LINES).format(
                opponent=opponent.app.name,
                target=notorious.app.name,
            )
        else:
            quiet = [sprite for sprite in alive if not sprite.is_saying]
            speaker = self._rng.choice(quiet or alive)
            line = self._rng.choice(SPECTATOR_LINES).format(
                a=first.app.name,
                b=second.app.name,
            )
        speaker.say(line, 2_200)
        self._crowd_timer.start(self._rng.randint(3_500, 7_000))

    def _taunt(self, token: int, sprite: AppSprite, line: str) -> None:
        if token != self._token or self._active is None:
            return
        if not all(item.is_alive for item in self._active):
            self._finish(token)
            return
        sprite.say(line, 1_050)

    def _finish(self, token: int) -> None:
        if token != self._token:
            return

        self._crowd_timer.stop()
        self._join_timer.stop()
        pair = self._active
        self._active = None
        self._midpoint = None

        notorious = self._notorious_fighter
        notorious_opponent = self._notorious_opponent
        helpers = [sprite for sprite in self._notorious_helpers if sprite.is_alive]
        self._notorious_fighter = None
        self._notorious_opponent = None
        self._notorious_helpers = []
        self._end_spectators()

        chase_started = False
        if pair is not None:
            first, second = pair
            self._relationships.record_fight(
                first.app.app_id,
                second.app.app_id,
                time.monotonic(),
            )
            both_alive = first.is_alive and second.is_alive
            guaranteed = (
                both_alive
                and notorious is not None
                and notorious_opponent is not None
                and notorious in pair
                and notorious_opponent in pair
                and bool(helpers)
            )
            knocked_down: AppSprite | None = None

            for sprite in pair:
                if sprite.is_alive:
                    sprite.end_fight()

            if guaranteed:
                if self._rng.random() < 0.5:
                    self._start_chase(notorious, notorious_opponent, helpers)
                    chase_started = self._chase_target is not None
                else:
                    notorious.knock_down()
                    knocked_down = notorious
            elif both_alive and self._rng.random() < KNOCKDOWN_CHANCE:
                knocked_down = self._rng.choice([first, second])
                knocked_down.knock_down()

            if both_alive and not chase_started:
                if first is not knocked_down:
                    first_line = self._rng.choice(BAD_LINES).format(name=second.app.name)
                    QTimer.singleShot(600, lambda: self._badmouth(first, first_line))
                if second is not knocked_down:
                    second_line = self._rng.choice(BAD_LINES).format(name=first.app.name)
                    QTimer.singleShot(2_400, lambda: self._badmouth(second, second_line))

        self._clear_cloud()
        if not chase_started:
            self._global_ready = time.monotonic() + GLOBAL_COOLDOWN + self._rng.uniform(0.0, 8.0)
        self._token += 1

    def _start_chase(
        self,
        notorious: AppSprite,
        opponent: AppSprite,
        helpers: list[AppSprite],
    ) -> None:
        chasers = [opponent]
        chasers.extend(sprite for sprite in helpers if sprite is not opponent and sprite.is_alive)
        if not chasers or not notorious.is_alive:
            if notorious.is_alive:
                notorious.knock_down()
            return

        centers = [sprite.center_scene for sprite in chasers]
        centroid = QPointF(
            sum(point.x() for point in centers) / len(centers),
            sum(point.y() for point in centers) / len(centers),
        )
        self._chase_target = notorious
        self._chasers = chasers
        now = time.monotonic()
        self._chase_grace_until = now + CHASE_HEAD_START
        self._chase_deadline = now + CHASE_HEAD_START + CHASE_SECONDS
        direction = self._best_flee_direction(notorious, chasers)
        notorious.start_flee(centroid, direction=direction)
        for sprite in chasers:
            if sprite.is_alive:
                sprite.start_chase(notorious, delay=CHASE_HEAD_START)
        self._chase_timer.start()

    def _best_flee_direction(
        self,
        notorious: AppSprite,
        chasers: list[AppSprite],
    ) -> QPointF:
        rect = self._scene.sceneRect()
        origin = notorious.center_scene
        centers = [sprite.center_scene for sprite in chasers]
        best_score = -1.0
        best = QPointF(1.0, 0.0)

        for index in range(24):
            angle = index * math.tau / 24.0
            ux = math.cos(angle)
            uy = math.sin(angle)
            score = 10_000.0
            for step in (80.0, 160.0, 240.0):
                px = origin.x() + ux * step
                py = origin.y() + uy * step
                if (
                    px < rect.left() + 48.0
                    or px > rect.right() - 48.0
                    or py < rect.top() + 48.0
                    or py > rect.bottom() - 48.0
                ):
                    score = -1.0
                    break
                for center in centers:
                    score = min(score, math.hypot(px - center.x(), py - center.y()))
            if score > best_score:
                best_score = score
                best = QPointF(ux, uy)

        return best

    def _check_chase(self) -> None:
        notorious = self._chase_target
        if notorious is None:
            self._chase_timer.stop()
            return
        if not notorious.is_alive:
            self._finish_chase(caught=False)
            return

        self._chasers = [sprite for sprite in self._chasers if sprite.is_alive]
        if not self._chasers:
            self._finish_chase(caught=False)
            return

        notorious_center = notorious.center_scene
        caught = False
        for chaser in self._chasers:
            center = chaser.center_scene
            if (
                math.hypot(center.x() - notorious_center.x(), center.y() - notorious_center.y())
                <= 60.0
            ):
                caught = True
                break
        if caught:
            self._finish_chase(caught=True)
        elif time.monotonic() >= self._chase_deadline:
            self._finish_chase(caught=False)

    def _finish_chase(self, caught: bool) -> None:
        notorious = self._chase_target
        chasers = list(self._chasers)
        self._chase_target = None
        self._chasers = []
        self._chase_grace_until = 0.0
        self._chase_timer.stop()
        if notorious is None:
            return

        if caught:
            if notorious.is_alive:
                self._scene.addItem(FightCloud(notorious.center_scene, 1_200))
                notorious.knock_down()
        elif notorious.is_alive:
            notorious.end_chase()

        for chaser in chasers:
            if chaser.is_alive:
                chaser.end_chase()

        if not caught and notorious.is_alive:
            alive = [chaser for chaser in chasers if chaser.is_alive]
            if alive:
                speaker = self._rng.choice(alive)
                line = self._rng.choice(THREAT_LINES).format(name=notorious.app.name)
                speaker.say(line, 2_600)

        self._global_ready = time.monotonic() + GLOBAL_COOLDOWN + self._rng.uniform(0.0, 8.0)

    def _abort_chase(self) -> None:
        notorious = self._chase_target
        chasers = list(self._chasers)
        self._chase_target = None
        self._chasers = []
        self._chase_grace_until = 0.0
        self._chase_timer.stop()
        if notorious is not None and notorious.is_alive:
            notorious.end_chase()
        for chaser in chasers:
            if chaser.is_alive:
                chaser.end_chase()

    @staticmethod
    def _badmouth(sprite: AppSprite, line: str) -> None:
        if (
            sprite.is_alive
            and sprite.is_grudging
            and not sprite.is_fighting
            and not sprite.is_chatting
            and not sprite.is_knocked_down
        ):
            sprite.say(line, 2_600)
