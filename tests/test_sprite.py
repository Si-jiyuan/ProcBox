from __future__ import annotations

import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QGraphicsScene

from procbox.core.models import AppInfo
from procbox.core.motion import Motion
from procbox.ui.face import Expression
from procbox.ui.fight import FightDirector
from procbox.ui.sprite import AppSprite


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app


def make_sprite(rng: random.Random | None = None) -> AppSprite:
    app = AppInfo(
        app_id="/Applications/Test.app",
        name="Test",
        pids=(10, 11),
        bundle_path="/Applications/Test.app",
    )
    sprite = AppSprite(app, rng=rng or random.Random(1))
    sprite.place(120.0, 240.0)
    return sprite


def test_sprite_layers_lower_icons_on_top(qapp: QApplication) -> None:
    sprite = make_sprite()
    assert sprite.zValue() == sprite.y() + sprite.size

    sprite.place(120.0, 340.0)
    assert sprite.zValue() == sprite.y() + sprite.size


def test_sprite_dies_and_revives(qapp: QApplication) -> None:
    sprite = make_sprite()

    sprite.die()
    assert not sprite.is_alive
    assert sprite._gray_pixmap is not None

    sprite.revive()
    assert sprite.is_alive
    assert sprite._gray_pixmap is None


def test_sprite_wanders_and_takes_breaks(qapp: QApplication) -> None:
    sprite = make_sprite(random.Random(5))
    start = (sprite.x(), sprite.y())
    saw_rest = False

    for _ in range(500):
        sprite.advance(0.1, 800.0, 600.0)
        saw_rest = saw_rest or sprite.is_resting

    assert saw_rest
    assert (sprite.x(), sprite.y()) != start


def test_sprite_switches_expressions(qapp: QApplication) -> None:
    sprite = make_sprite(random.Random(9))
    expressions = {sprite.expression}

    for _ in range(1_200):
        sprite.advance(0.1, 800.0, 600.0)
        expressions.add(sprite.expression)

    assert len(expressions) > 1
    assert Expression.DEAD not in expressions


def test_chat_bubble_and_death_state(qapp: QApplication) -> None:
    sprite = make_sprite(random.Random(3))

    sprite.begin_chat()
    assert sprite.is_chatting
    assert not sprite.is_resting

    sprite.look_toward(QPointF(500.0, 500.0))
    sprite.say("hello", 5_000)
    assert sprite.is_saying
    assert sprite._bubble._text == "hello"

    sprite.end_chat()
    assert not sprite.is_chatting

    sprite.die()
    assert sprite.expression is Expression.DEAD
    assert not sprite.is_saying


def test_advance_requests_repaint_without_hover(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprite = make_sprite(random.Random(2))
    calls: list[int] = []
    original_update = AppSprite.update

    def tracked_update(self) -> None:
        calls.append(1)
        original_update(self)

    monkeypatch.setattr(AppSprite, "update", tracked_update)
    sprite.advance(0.05, 800.0, 600.0)

    assert calls


def test_feet_face_the_movement_direction(qapp: QApplication) -> None:
    sprite = make_sprite(random.Random(4))
    sprite.place(300.0, 300.0)

    sprite._motion = Motion(300.0, 300.0, -40.0, 0.0)
    sprite.advance(0.05, 800.0, 600.0)
    assert sprite._facing == -1.0

    sprite._motion = Motion(sprite.x(), sprite.y(), 40.0, 0.0)
    sprite.advance(0.05, 800.0, 600.0)
    assert sprite._facing == 1.0


def test_collision_starts_a_fight(qapp: QApplication) -> None:
    scene = QGraphicsScene()
    scene.setSceneRect(0.0, 0.0, 800.0, 600.0)

    first = make_sprite(random.Random(5))
    second = make_sprite(random.Random(6))
    scene.addItem(first)
    scene.addItem(second)
    first.move_center_to(QPointF(250.0, 250.0))
    second.move_center_to(QPointF(295.0, 265.0))

    director = FightDirector(
        scene,
        {"first": first, "second": second},
        random.Random(1),
    )
    director._check_collisions()

    assert director._active is not None
    assert first.is_fighting
    assert second.is_fighting
    assert first._facing == 1.0
    assert second._facing == -1.0

    director.stop()
    assert not first.is_fighting
    assert not second.is_fighting
