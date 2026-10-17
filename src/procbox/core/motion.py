from __future__ import annotations

import math
import random
from dataclasses import dataclass

MIN_SPEED = 18.0
MAX_SPEED = 52.0
TURN_RATE = 0.9


@dataclass(frozen=True, slots=True)
class Motion:
    x: float
    y: float
    vx: float
    vy: float

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)


def random_velocity(rng: random.Random) -> tuple[float, float]:
    angle = rng.uniform(0.0, math.tau)
    speed = rng.uniform(MIN_SPEED, MAX_SPEED)
    return math.cos(angle) * speed, math.sin(angle) * speed


def step(
    motion: Motion,
    dt: float,
    width: float,
    height: float,
    box_size: float,
    rng: random.Random,
) -> Motion:
    """Advance one sprite, wandering gently and bouncing off the pen walls.

    Collisions between sprites are intentionally ignored: they pass through
    each other and are layered by their y position instead.
    """

    speed = motion.speed
    if speed == 0.0:
        vx, vy = random_velocity(rng)
        speed = math.hypot(vx, vy)
    else:
        angle = math.atan2(motion.vy, motion.vx) + rng.gauss(0.0, TURN_RATE) * dt
        speed = min(max(speed, MIN_SPEED), MAX_SPEED)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed

    x = motion.x + vx * dt
    y = motion.y + vy * dt

    max_x = max(0.0, width - box_size)
    max_y = max(0.0, height - box_size)

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

    return Motion(x=x, y=y, vx=vx, vy=vy)
