from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from procbox.ui.sprite import AppSprite

COLLISION_DISTANCE = 58.0
WALL_RESTITUTION = 0.72
IMPULSE_COOLDOWN = 0.35
MIN_BOUNCE_SPEED = 140.0
MIN_ENERGY = 0.1


class ThrowPhysics:
    """Small 2D physics layer for icons that are dragged and thrown."""

    def __init__(self, sprites: dict[str, AppSprite], rng: random.Random) -> None:
        self._sprites = sprites
        self._rng = rng
        self._last_impulse: dict[tuple[int, int], float] = {}

    def step(self, dt: float, width: float, height: float) -> None:
        movers = [sprite for sprite in self._sprites.values() if sprite.is_physics_active]
        if not movers:
            self._last_impulse.clear()
            return

        for mover in movers:
            if not mover.is_alive or mover.is_dragging:
                mover.stop_physics()
                continue
            speed = mover.physics_speed
            steps = max(1, min(8, int(math.ceil(speed * dt / 12.0))))
            substep = dt / steps
            for _ in range(steps):
                if not mover.is_physics_active:
                    break
                mover.integrate_physics(substep, width, height)
                self._collide(mover, width, height)
            if mover.is_physics_active:
                mover.apply_physics_friction(dt)

    def _collide(self, mover: AppSprite, width: float, height: float) -> None:
        mover_center = mover.center_scene
        mover_vx, mover_vy = mover.physics_velocity

        for other in list(self._sprites.values()):
            if other is mover or not other.is_alive or other.is_dragging:
                continue
            if other.is_physics_active and id(mover) > id(other):
                continue

            center = other.center_scene
            dx = center.x() - mover_center.x()
            dy = center.y() - mover_center.y()
            distance = math.hypot(dx, dy)
            if distance >= COLLISION_DISTANCE:
                continue

            if distance < 1e-6:
                angle = self._rng.uniform(0.0, math.tau)
                nx, ny = math.cos(angle), math.sin(angle)
            else:
                nx = dx / distance
                ny = dy / distance
            overlap = COLLISION_DISTANCE - distance

            key = (min(id(mover), id(other)), max(id(mover), id(other)))
            now = time.monotonic()
            if now - self._last_impulse.get(key, 0.0) < IMPULSE_COOLDOWN:
                # They are already moving apart from the last bounce. Do not
                # keep correcting their positions every frame, which causes
                # the visible twitching in dense groups.
                continue

            self._last_impulse[key] = now
            speed = math.hypot(mover_vx, mover_vy)
            # Halve the energy each impact, quantized to 0.1 units.
            energy = max(
                MIN_ENERGY,
                (max(1, int(round(mover.physics_energy * 10.0)) // 2)) / 10.0,
            )
            mover.set_physics_energy(energy)
            tangent_x = -ny
            tangent_y = nx
            tangent = mover_vx * tangent_x + mover_vy * tangent_y
            bounce = max(MIN_BOUNCE_SPEED, speed * energy)

            if other.can_be_bumped:
                mover.shift_physics_center(
                    nx * overlap * 0.5,
                    ny * overlap * 0.5,
                    width,
                    height,
                )
                other.shift_physics_center(
                    -nx * overlap * 0.5,
                    -ny * overlap * 0.5,
                    width,
                    height,
                )
                other.bump_physics(
                    nx * bounce * 0.9 + tangent_x * tangent * 0.2,
                    ny * bounce * 0.9 + tangent_y * tangent * 0.2,
                    spin=-bounce * 0.04,
                    energy=energy,
                )
                other.add_physics_impact()
            else:
                mover.shift_physics_center(nx * overlap, ny * overlap, width, height)

            mover.set_physics_velocity(
                -nx * bounce + tangent_x * tangent * 0.6,
                -ny * bounce + tangent_y * tangent * 0.6,
            )
            mover.add_physics_impact()

            # Bounce off at most one object in this substep. Chaining several
            # impulses in the same frame is what caused the twitching.
            return
