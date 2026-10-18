from __future__ import annotations

from procbox.core.relationships import RelationshipBook


def test_friendly_chat_prevents_immediate_fight() -> None:
    book = RelationshipBook()
    book.record_chat("a", "b", now=100.0)

    assert book.fight_multiplier("a", "b", now=101.0) == 0.0
    assert book.fight_multiplier("b", "a", now=114.0) == 0.0
    assert book.fight_multiplier("a", "b", now=116.0) < 1.0


def test_fighting_makes_a_pair_more_likely_to_fight_again() -> None:
    book = RelationshipBook()
    book.record_fight("a", "b", now=100.0)

    assert book.fight_multiplier("a", "b", now=120.0) > 1.0


def test_more_chats_make_best_friends_less_likely_to_fight() -> None:
    book = RelationshipBook()
    for i in range(4):
        book.record_chat("a", "b", now=100.0 + i)

    multiplier = book.fight_multiplier("a", "b", now=130.0)
    assert 0.0 < multiplier < 0.2


def test_three_distinct_fight_partners_make_an_app_notorious() -> None:
    book = RelationshipBook()
    book.record_fight("a", "b")
    book.record_fight("a", "c")
    assert not book.is_notorious("a")

    book.record_fight("a", "d")
    assert book.is_notorious("a")
    assert book.fight_partners("a") == {"b", "c", "d"}


def test_relationship_records_expire_after_30_minutes() -> None:
    book = RelationshipBook()
    book.record_fight("a", "b", now=100.0)
    book.record_fight("a", "c", now=100.0)
    book.record_fight("a", "d", now=100.0)

    assert book.get_bond("a", "b", now=1_900.0) is not None
    assert book.is_notorious("a", now=1_900.0)

    expired_at = 100.0 + 30 * 60 + 1
    assert book.get_bond("a", "b", now=expired_at) is None
    assert book.fight_multiplier("a", "b", now=expired_at) == 1.0
    assert not book.is_notorious("a", now=expired_at)
