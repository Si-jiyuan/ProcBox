from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QEasingCurve, QObject, QPointF, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QGraphicsScene

from procbox import config
from procbox.core.relationships import RelationshipBook

if TYPE_CHECKING:
    from procbox.ui.sprite import AppSprite

CARE_RADIUS = 260.0
CARE_OFFSET = 56.0
BODY_CENTER_X = config.BODY_X + config.BODY_SIZE / 2.0
BODY_CENTER_Y = config.BODY_Y + config.BODY_SIZE / 2.0


@dataclass
class _CareSession:
    downed: AppSprite
    friend: AppSprite
    token: int
    animation: QPropertyAnimation | None = None


class CareDirector(QObject):
    """Lets friends walk over and help a knocked-down app back to its feet."""

    def __init__(
        self,
        scene: QGraphicsScene,
        sprites: dict[str, AppSprite],
        relationships: RelationshipBook,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._scene = scene
        self._sprites = sprites
        self._relationships = relationships
        self._sessions: dict[str, _CareSession] = {}
        self._token = 0

        self._timer = QTimer(self)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self._check)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        for key in list(self._sessions):
            self._cancel(key)

    def interrupt_for(self, sprite: AppSprite) -> None:
        for key, session in list(self._sessions.items()):
            if session.downed is sprite or session.friend is sprite:
                self._cancel(key)

    def _check(self) -> None:
        for key, session in list(self._sessions.items()):
            if (
                not session.downed.is_alive
                or not session.downed.is_knocked_down
                or not session.friend.is_alive
                or not session.friend.is_caring
            ):
                self._cancel(key)

        for downed in self._sprites.values():
            if not downed.is_alive or not downed.is_knocked_down:
                continue
            if downed.app.app_id in self._sessions:
                continue
            friend = self._find_friend(downed)
            if friend is not None:
                self._start(downed, friend)

    def _find_friend(self, downed: AppSprite) -> AppSprite | None:
        candidates: list[tuple[float, AppSprite]] = []
        for friend in self._sprites.values():
            if friend is downed or not friend.is_alive:
                continue
            if friend.is_activity_animating:
                continue
            if friend.is_chatting or friend.is_fighting or friend.is_spectating:
                continue
            if friend.is_helping or friend.is_fleeing or friend.is_chasing:
                continue
            if friend.is_caring or friend.is_dragging or friend.is_physics_active:
                continue
            if friend.is_recovering or friend.is_knocked_down:
                continue
            bond = self._relationships.get_bond(
                downed.app.app_id,
                friend.app.app_id,
            )
            if bond is None or bond.chats <= 0:
                continue
            distance = math.hypot(
                friend.center_scene.x() - downed.center_scene.x(),
                friend.center_scene.y() - downed.center_scene.y(),
            )
            if distance <= CARE_RADIUS:
                candidates.append((distance, friend))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _start(self, downed: AppSprite, friend: AppSprite) -> None:
        self._token += 1
        token = self._token
        key = downed.app.app_id
        friend.begin_care(downed.center_scene)

        side = 1.0 if friend.center_scene.x() >= downed.center_scene.x() else -1.0
        target_center = QPointF(
            downed.center_scene.x() + side * CARE_OFFSET,
            downed.center_scene.y(),
        )
        rect = self._scene.sceneRect()
        max_x = max(0.0, rect.width() - config.SPRITE_LOGICAL_SIZE)
        max_y = max(0.0, rect.height() - config.SPRITE_LOGICAL_SIZE)
        target = QPointF(
            min(max(target_center.x() - BODY_CENTER_X, 0.0), max_x),
            min(max(target_center.y() - BODY_CENTER_Y, 0.0), max_y),
        )
        distance = math.hypot(
            friend.center_scene.x() - target_center.x(),
            friend.center_scene.y() - target_center.y(),
        )

        session = _CareSession(downed=downed, friend=friend, token=token)
        self._sessions[key] = session

        animation = QPropertyAnimation(friend, b"pos", self)
        animation.setDuration(max(300, min(1_600, int(distance / 130.0 * 1_000.0))))
        animation.setStartValue(friend.pos())
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        animation.valueChanged.connect(
            lambda value, sprite=friend: sprite.setZValue(value.y() + sprite.size)
        )
        animation.finished.connect(lambda: self._arrived(token, key))
        session.animation = animation
        animation.start()

    def _arrived(self, token: int, key: str) -> None:
        session = self._sessions.get(key)
        if session is None or session.token != token:
            return
        if not session.downed.is_knocked_down or not session.friend.is_alive:
            self._cancel(key)
            return

        session.friend.say(
            f"{session.downed.app.name} 你没事吧？我来扶你！",
            2_400,
        )
        QTimer.singleShot(700, lambda: self._lift(token, key))

    def _lift(self, token: int, key: str) -> None:
        session = self._sessions.get(key)
        if session is None or session.token != token:
            return
        if not session.downed.is_knocked_down:
            self._cancel(key)
            return

        session.downed.get_up()
        self._relationships.record_chat(
            session.friend.app.app_id,
            session.downed.app.app_id,
        )
        session.downed.say(f"谢谢 {session.friend.app.name}…", 2_200)
        QTimer.singleShot(900, lambda: self._finish(token, key))

    def _finish(self, token: int, key: str) -> None:
        session = self._sessions.get(key)
        if session is None or session.token != token:
            return
        self._sessions.pop(key, None)
        if session.friend.is_alive:
            session.friend.end_care()

    def _cancel(self, key: str) -> None:
        session = self._sessions.pop(key, None)
        if session is None:
            return
        if session.animation is not None:
            session.animation.stop()
            session.animation.deleteLater()
        if session.friend.is_alive and session.friend.is_caring:
            session.friend.end_care()
