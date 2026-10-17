from __future__ import annotations

import os
import random
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QGraphicsScene

from procbox.core.models import AppInfo
from procbox.core.motion import Motion
from procbox.core.relationships import RelationshipBook
from procbox.ui.care import CareDirector
from procbox.ui.chat import CONVERSATIONS
from procbox.ui.face import Expression
from procbox.ui.fight import BAD_LINES, SPECTATOR_LINES, FightCloud, FightDirector
from procbox.ui.sprite import AppSprite


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app


def make_sprite(
    rng: random.Random | None = None,
    app_id: str = "/Applications/Test.app",
    name: str = "Test",
) -> AppSprite:
    app = AppInfo(
        app_id=app_id,
        name=name,
        pids=(10, 11),
        bundle_path=app_id,
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
    spectator = make_sprite(random.Random(7))
    scene.addItem(first)
    scene.addItem(second)
    scene.addItem(spectator)
    first.move_center_to(QPointF(250.0, 250.0))
    second.move_center_to(QPointF(295.0, 265.0))
    spectator.move_center_to(QPointF(355.0, 300.0))

    director = FightDirector(
        scene,
        {"first": first, "second": second, "spectator": spectator},
        random.Random(1),
    )
    director._check_collisions()

    assert director._active is not None
    assert first.is_fighting
    assert second.is_fighting
    assert first._facing == 1.0
    assert second._facing == -1.0
    assert spectator.is_spectating
    assert spectator in director._spectators

    director.stop()
    assert not first.is_fighting
    assert not second.is_fighting
    assert not spectator.is_spectating


def test_fight_leaves_a_long_angry_grudge(qapp: QApplication) -> None:
    sprite = make_sprite(random.Random(11))
    sprite.begin_fight(QPointF(500.0, 500.0))
    sprite.end_fight()

    assert sprite.is_grudging
    assert 5.0 <= sprite.grudge_remaining <= 60.0
    assert sprite.expression is Expression.ANGRY

    for _ in range(40):
        sprite.advance(0.1, 800.0, 600.0)

    assert sprite.is_grudging
    assert sprite.expression is Expression.ANGRY


def test_social_lines_always_name_the_other_app(qapp: QApplication) -> None:
    for conversation in CONVERSATIONS:
        for line in conversation:
            assert "TestApp" in line.format(name="TestApp")

    for line in BAD_LINES:
        assert "TestApp" in line.format(name="TestApp")

    for line in SPECTATOR_LINES:
        assert line.format(a="FirstApp", b="SecondApp")


def test_bubble_expands_with_longer_content(qapp: QApplication) -> None:
    sprite = make_sprite(random.Random(8))

    sprite.say("短句", 5_000)
    short_size = (sprite._bubble._width, sprite._bubble._height)

    sprite.say("这是一条很长的测试消息，用来确认聊天气泡会随着内容一起变大。" * 4, 5_000)
    long_size = (sprite._bubble._width, sprite._bubble._height)

    assert long_size[0] > short_size[0]
    assert long_size[1] > short_size[1]


def test_sprite_steers_around_a_fight_zone(qapp: QApplication) -> None:
    sprite = make_sprite(random.Random(12))
    sprite.move_center_to(QPointF(400.0, 300.0))
    sprite._motion = Motion(sprite.x(), sprite.y(), 0.0, 40.0)

    zone_center = QPointF(400.0, 400.0)
    sprite.advance(0.05, 800.0, 600.0, (zone_center, 175.0))

    dx = sprite.center_scene.x() - zone_center.x()
    dy = sprite.center_scene.y() - zone_center.y()
    assert (dx * dx + dy * dy) ** 0.5 >= 174.0


def test_knock_down_closes_eyes_and_gets_up(qapp: QApplication) -> None:
    sprite = make_sprite(random.Random(13))
    sprite.knock_down(duration=0.5)

    assert sprite.is_knocked_down
    assert sprite.expression is Expression.SLEEPY

    sprite.advance(0.2, 800.0, 600.0)
    assert sprite.is_knocked_down

    sprite.advance(0.4, 800.0, 600.0)
    assert not sprite.is_knocked_down


def test_fight_cloud_can_be_dismissed_twice(qapp: QApplication) -> None:
    scene = QGraphicsScene()
    scene.setSceneRect(0.0, 0.0, 400.0, 400.0)
    cloud = FightCloud(QPointF(200.0, 200.0), 1_000)
    scene.addItem(cloud)

    cloud.dismiss()
    cloud.dismiss()


def test_fighters_stay_angry_for_the_whole_fight(qapp: QApplication) -> None:
    first = make_sprite(random.Random(20))
    second = make_sprite(random.Random(21))
    first.begin_fight(second.center_scene)
    second.begin_fight(first.center_scene)

    for _ in range(30):
        first.advance(0.1, 800.0, 600.0)
        second.advance(0.1, 800.0, 600.0)

    assert first.expression is Expression.ANGRY
    assert second.expression is Expression.ANGRY


def test_helpers_are_angry_and_chase_states_move(qapp: QApplication) -> None:
    runner = make_sprite(random.Random(22))
    chaser = make_sprite(random.Random(23))
    helper = make_sprite(random.Random(24))
    runner.move_center_to(QPointF(300.0, 300.0))
    chaser.move_center_to(QPointF(400.0, 300.0))
    helper.move_center_to(QPointF(420.0, 300.0))

    helper.begin_help(runner.center_scene)
    assert helper.is_helping
    assert helper.expression is Expression.ANGRY

    runner.start_flee(chaser.center_scene)
    chaser.start_chase(runner)
    helper.start_chase(runner)
    runner_start = (runner.x(), runner.y())
    chaser_start = (chaser.x(), chaser.y())

    for _ in range(5):
        runner.advance(0.1, 800.0, 600.0)
        chaser.advance(0.1, 800.0, 600.0)
        helper.advance(0.1, 800.0, 600.0)

    assert (runner.x(), runner.y()) != runner_start
    assert (chaser.x(), chaser.y()) != chaser_start
    assert helper.is_chasing
    assert helper.expression is Expression.ANGRY


def test_notorious_app_helpers_and_fight_cooldown(qapp: QApplication) -> None:
    scene = QGraphicsScene()
    scene.setSceneRect(0.0, 0.0, 900.0, 600.0)

    bully = make_sprite(random.Random(30), "/Applications/Bully.app", "Bully")
    victim = make_sprite(random.Random(31), "/Applications/Victim.app", "Victim")
    helpers = [
        make_sprite(random.Random(32 + index), f"/Applications/Helper{index}.app", f"Helper{index}")
        for index in range(3)
    ]
    for sprite in [bully, victim, *helpers]:
        scene.addItem(sprite)

    bully.move_center_to(QPointF(450.0, 300.0))
    victim.move_center_to(QPointF(505.0, 310.0))
    for index, helper in enumerate(helpers):
        helper.move_center_to(QPointF(340.0 + index * 110.0, 220.0 + index * 50.0))

    relationships = RelationshipBook()
    for helper in helpers:
        relationships.record_fight(bully.app.app_id, helper.app.app_id)

    sprites = {
        "bully": bully,
        "victim": victim,
        **{f"helper{index}": helper for index, helper in enumerate(helpers)},
    }
    director = FightDirector(
        scene,
        sprites,
        random.Random(5),
        relationships=relationships,
    )
    director._start_fight(bully, victim, (id(bully), id(victim)), time.monotonic())

    assert director._notorious_fighter is bully
    assert set(director._notorious_helpers) == set(helpers)
    assert all(helper.is_helping for helper in helpers)
    assert all(helper.expression is Expression.ANGRY for helper in helpers)

    director._finish(director._token)
    if director._chase_target is not None:
        director._finish_chase(caught=False)
    assert director._global_ready - time.monotonic() >= 19.0

    director.stop()


def test_friendly_pair_does_not_start_a_fight(qapp: QApplication) -> None:
    scene = QGraphicsScene()
    scene.setSceneRect(0.0, 0.0, 800.0, 600.0)

    first = make_sprite(random.Random(40), "/Applications/First.app", "First")
    second = make_sprite(random.Random(41), "/Applications/Second.app", "Second")
    scene.addItem(first)
    scene.addItem(second)
    first.move_center_to(QPointF(250.0, 250.0))
    second.move_center_to(QPointF(295.0, 265.0))

    relationships = RelationshipBook()
    relationships.record_chat(first.app.app_id, second.app.app_id, time.monotonic())

    director = FightDirector(
        scene,
        {"first": first, "second": second},
        random.Random(1),
        relationships=relationships,
    )
    director._check_collisions()

    assert director._active is None
    director.stop()


def test_spectator_gathers_gradually(qapp: QApplication) -> None:
    sprite = make_sprite(random.Random(50))
    sprite.move_center_to(QPointF(200.0, 200.0))
    sprite.begin_watch(QPointF(500.0, 300.0))
    sprite.set_watch_target(QPointF(500.0, 300.0), 800.0, 600.0)

    start = (sprite.x(), sprite.y())
    sprite.advance(0.1, 800.0, 600.0)
    after_one_tick = (sprite.x(), sprite.y())

    assert after_one_tick != start
    assert sprite.is_gathering

    for _ in range(50):
        sprite.advance(0.1, 800.0, 600.0)

    assert not sprite.is_gathering


def test_friend_helps_knocked_down_app(qapp: QApplication) -> None:
    scene = QGraphicsScene()
    scene.setSceneRect(0.0, 0.0, 800.0, 600.0)
    downed = make_sprite(random.Random(51), "/Applications/Downed.app", "Downed")
    friend = make_sprite(random.Random(52), "/Applications/Friend.app", "Friend")
    scene.addItem(downed)
    scene.addItem(friend)
    downed.move_center_to(QPointF(350.0, 300.0))
    friend.move_center_to(QPointF(500.0, 320.0))
    downed.knock_down(duration=30.0)

    relationships = RelationshipBook()
    relationships.record_chat(downed.app.app_id, friend.app.app_id)

    director = CareDirector(scene, {"downed": downed, "friend": friend}, relationships)
    director._check()

    session = director._sessions.get(downed.app.app_id)
    assert session is not None
    assert friend.is_caring

    director._arrived(session.token, downed.app.app_id)
    director._lift(session.token, downed.app.app_id)

    assert not downed.is_knocked_down

    director._finish(session.token, downed.app.app_id)
    assert not friend.is_caring
    director.stop()
