from __future__ import annotations

import time
from dataclasses import dataclass, field

FRIENDLY_GRACE_SECONDS = 15.0
NOTORIOUS_PARTNER_COUNT = 3
RELATION_TTL_SECONDS = 30 * 60


@dataclass
class Bond:
    chats: int = 0
    fights: int = 0
    friendly_until: float = 0.0
    last_chat: float = 0.0
    last_fight: float = 0.0
    updated_at: float = 0.0


@dataclass
class RelationshipBook:
    """In-memory relationship history between app pairs."""

    _bonds: dict[tuple[str, str], Bond] = field(default_factory=dict)

    @staticmethod
    def _key(first: str, second: str) -> tuple[str, str]:
        return (first, second) if first <= second else (second, first)

    def _prune(self, now: float) -> None:
        expired = [
            key for key, bond in self._bonds.items() if now - bond.updated_at > RELATION_TTL_SECONDS
        ]
        for key in expired:
            self._bonds.pop(key, None)

    def get_bond(
        self,
        first: str,
        second: str,
        now: float | None = None,
    ) -> Bond | None:
        timestamp = time.monotonic() if now is None else now
        self._prune(timestamp)
        return self._bonds.get(self._key(first, second))

    def bond(self, first: str, second: str, now: float | None = None) -> Bond:
        timestamp = time.monotonic() if now is None else now
        self._prune(timestamp)
        key = self._key(first, second)
        bond = self._bonds.get(key)
        if bond is None:
            bond = Bond(updated_at=timestamp)
            self._bonds[key] = bond
        return bond

    def record_chat(self, first: str, second: str, now: float | None = None) -> None:
        timestamp = time.monotonic() if now is None else now
        bond = self.bond(first, second, timestamp)
        bond.updated_at = timestamp
        bond.chats += 1
        bond.last_chat = timestamp
        bond.friendly_until = timestamp + FRIENDLY_GRACE_SECONDS

    def record_fight(self, first: str, second: str, now: float | None = None) -> None:
        timestamp = time.monotonic() if now is None else now
        bond = self.bond(first, second, timestamp)
        bond.updated_at = timestamp
        bond.fights += 1
        bond.last_fight = timestamp
        bond.friendly_until = 0.0

    def fight_multiplier(
        self,
        first: str,
        second: str,
        now: float | None = None,
    ) -> float:
        timestamp = time.monotonic() if now is None else now
        bond = self.get_bond(first, second, timestamp)
        if bond is None:
            return 1.0
        if timestamp < bond.friendly_until:
            return 0.0
        multiplier = 1.0 + 0.75 * bond.fights - 0.5 * bond.chats
        return min(4.0, max(0.08, multiplier))

    def fight_partners(self, app_id: str, now: float | None = None) -> set[str]:
        timestamp = time.monotonic() if now is None else now
        self._prune(timestamp)
        partners: set[str] = set()
        for (first, second), bond in self._bonds.items():
            if bond.fights <= 0:
                continue
            if first == app_id:
                partners.add(second)
            elif second == app_id:
                partners.add(first)
        return partners

    def is_notorious(self, app_id: str, now: float | None = None) -> bool:
        return len(self.fight_partners(app_id, now)) >= NOTORIOUS_PARTNER_COUNT
