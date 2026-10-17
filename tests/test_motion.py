from __future__ import annotations

import random

from procbox.core.motion import MAX_SPEED, MIN_SPEED, Motion, random_velocity, step


def test_random_velocity_respects_speed_bounds() -> None:
    rng = random.Random(42)
    for _ in range(200):
        vx, vy = random_velocity(rng)
        speed = (vx * vx + vy * vy) ** 0.5
        assert MIN_SPEED <= speed <= MAX_SPEED


def test_sprite_stays_inside_the_pen() -> None:
    rng = random.Random(7)
    width, height, size = 800.0, 600.0, 64.0
    motion = Motion(x=100.0, y=100.0, vx=0.0, vy=0.0)

    for _ in range(5_000):
        motion = step(motion, 1.0 / 60.0, width, height, size, rng)
        assert 0.0 <= motion.x <= width - size
        assert 0.0 <= motion.y <= height - size


def test_bounce_flips_velocity_at_the_wall() -> None:
    rng = random.Random(1)
    motion = Motion(x=0.0, y=0.0, vx=-40.0, vy=-40.0)
    bounced = step(motion, 0.5, 400.0, 400.0, 64.0, rng)

    assert bounced.x == 0.0
    assert bounced.y == 0.0
    assert bounced.vx > 0.0
    assert bounced.vy > 0.0


def test_speed_is_preserved_while_wandering() -> None:
    rng = random.Random(3)
    motion = Motion(x=100.0, y=100.0, vx=30.0, vy=40.0)
    for _ in range(600):
        motion = step(motion, 1.0 / 60.0, 2_000.0, 2_000.0, 64.0, rng)
        assert MIN_SPEED <= motion.speed <= MAX_SPEED
