from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPointF, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsObject, QGraphicsScene

from procbox.core.relationships import RelationshipBook

if TYPE_CHECKING:
    from procbox.ui.sprite import AppSprite

CHATTER = [
    "今天也要开心呀 ✨",
    "摸鱼中 🐟",
    "咕噜咕噜…",
    "有人在看我吗？",
    "好困 💤",
    "别戳我啦！",
    "一起玩吗？",
    "嘘…主人在忙",
    "嘿嘿～",
    "我超可爱吧？",
]

CONVERSATIONS = [
    ("{name} 今天也超可爱！", "谢谢～{name} 也很棒！", "和 {name} 聊天真开心"),
    ("{name} 的图标好好看", "嘿嘿，{name} 也很有品味", "{name} 最靠谱了"),
    ("{name} 刚才帮了我大忙", "小事啦，{name} 也很厉害", "以后也要一起玩呀 {name}"),
    ("{name} 好聪明呀", "{name} 才是真的厉害", "我们是最好的朋友！{name}"),
    ("{name} 今天真精神", "{name} 也是！", "和 {name} 待在一起真好"),
    ("我最喜欢 {name} 了", "{name} 也是我的好朋友", "拉钩！{name}"),
    ("{name} 笑起来真好看", "因为和 {name} 在一起呀", "那以后多聊聊天吧 {name}"),
    ("{name} 做事真认真", "{name} 才是呢", "一起加油吧 {name}"),
]


def _heart_path(size: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(0.0, size * 0.55)
    path.cubicTo(
        -size * 1.15,
        -size * 0.1,
        -size * 0.6,
        -size * 0.95,
        0.0,
        -size * 0.35,
    )
    path.cubicTo(
        size * 0.6,
        -size * 0.95,
        size * 1.15,
        -size * 0.1,
        0.0,
        size * 0.55,
    )
    path.closeSubpath()
    return path


class HeartBurst(QGraphicsObject):
    """Floating hearts used as the visual spark of a conversation."""

    def __init__(self, center: QPointF) -> None:
        super().__init__()
        self.setPos(center)
        self.setZValue(1_000_000.0)
        self._progress = 0.0
        self._started = time.monotonic()
        self._duration = 2.4
        self._hearts = [(-17.0, 8.0, 0.0, 1.0), (6.0, 16.0, 0.12, 1.15), (22.0, -2.0, 0.28, 0.8)]

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def boundingRect(self) -> QRectF:
        return QRectF(-48.0, -64.0, 96.0, 100.0)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for dx, dy, delay, scale in self._hearts:
            local = max(0.0, (self._progress - delay) / (1.0 - delay))
            if local <= 0.0 or local >= 1.0:
                continue
            alpha = int(255 * min(1.0, math.sin(math.pi * local) * 1.5))
            if alpha <= 0:
                continue
            painter.save()
            painter.setOpacity(alpha / 255.0)
            painter.translate(dx, dy - local * 30.0)
            factor = scale * (0.7 + local * 0.35)
            painter.scale(factor, factor)
            painter.setPen(QPen(QColor(140, 48, 80), 1.2))
            painter.setBrush(QColor(255, 118, 150))
            painter.drawPath(_heart_path(11.0))
            painter.restore()

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started
        if elapsed >= self._duration:
            self._dispose()
            return
        self._progress = elapsed / self._duration
        self.update()

    def _dispose(self) -> None:
        self._timer.stop()
        scene = self.scene()
        if scene is not None:
            scene.removeItem(self)
        self.deleteLater()


class ChatDirector(QObject):
    """Schedules idle chatter and little conversations between app sprites."""

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
        self._active_pair: tuple[AppSprite, AppSprite] | None = None
        self._token = 0

        self._chat_timer = QTimer(self)
        self._chat_timer.setSingleShot(True)
        self._chat_timer.timeout.connect(self._maybe_chat)
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._random_bubble)

        self._chat_timer.start(self._rng.randint(5_000, 9_000))
        self._bubble_timer.start(self._rng.randint(2_500, 5_000))

    def stop(self) -> None:
        self._chat_timer.stop()
        self._bubble_timer.stop()
        self._token += 1
        if self._active_pair is not None:
            for sprite in self._active_pair:
                if sprite.is_alive:
                    sprite.end_chat()
            self._active_pair = None

    def _maybe_chat(self) -> None:
        try:
            if self._active_pair is not None:
                return
            alive = [
                sprite
                for sprite in self._sprites.values()
                if sprite.is_alive
                and not sprite.is_fighting
                and not sprite.is_spectating
                and not sprite.is_helping
                and not sprite.is_fleeing
                and not sprite.is_chasing
                and not sprite.is_caring
                and not sprite.is_knocked_down
                and not sprite.is_grudging
            ]
            if len(alive) < 2 or self._rng.random() < 0.25:
                return

            pairs: list[tuple[float, AppSprite, AppSprite]] = []
            for index, first in enumerate(alive):
                first_center = first.center_scene
                for second in alive[index + 1 :]:
                    second_center = second.center_scene
                    distance = math.hypot(
                        first_center.x() - second_center.x(),
                        first_center.y() - second_center.y(),
                    )
                    pairs.append((distance, first, second))

            pairs.sort(key=lambda item: item[0])
            distance, first, second = self._rng.choice(pairs[: min(8, len(pairs))])
            if distance > 560.0:
                return

            self._token += 1
            token = self._token
            self._active_pair = (first, second)
            first.begin_chat()
            second.begin_chat()
            first.look_toward(second.center_scene)
            second.look_toward(first.center_scene)

            midpoint = QPointF(
                (first.center_scene.x() + second.center_scene.x()) / 2.0,
                (first.center_scene.y() + second.center_scene.y()) / 2.0,
            )
            self._scene.addItem(HeartBurst(midpoint))

            lines = self._rng.choice(CONVERSATIONS)
            first_line = lines[0].format(name=second.app.name)
            second_line = lines[1].format(name=first.app.name)
            third_line = lines[2].format(name=second.app.name)
            QTimer.singleShot(450, lambda: self._say_step(token, first, first_line))
            QTimer.singleShot(1_550, lambda: self._say_step(token, second, second_line))
            QTimer.singleShot(2_650, lambda: self._say_step(token, first, third_line))
            QTimer.singleShot(4_200, lambda: self._finish_chat(token))
        finally:
            self._chat_timer.start(self._rng.randint(11_000, 20_000))

    def _say_step(self, token: int, sprite: AppSprite, text: str) -> None:
        if token != self._token or self._active_pair is None:
            return
        if not all(item.is_alive for item in self._active_pair):
            self._finish_chat(token)
            return
        sprite.say(text, 1_850)

    def _finish_chat(self, token: int) -> None:
        if token != self._token:
            return
        pair = self._active_pair
        self._active_pair = None
        if pair is not None:
            first, second = pair
            if first.is_alive and second.is_alive:
                self._relationships.record_chat(
                    first.app.app_id,
                    second.app.app_id,
                    time.monotonic(),
                )
            for sprite in pair:
                if sprite.is_alive:
                    sprite.end_chat()

    def _random_bubble(self) -> None:
        try:
            candidates = [
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
                and not sprite.is_grudging
                and not sprite.is_saying
            ]
            if candidates:
                sprite = self._rng.choice(candidates)
                sprite.say(self._rng.choice(CHATTER), self._rng.randint(2_200, 3_200))
        finally:
            self._bubble_timer.start(self._rng.randint(6_000, 11_000))
