# casino/tests/test_shoe.py
# The shared card shoe (casino.shoe): card format, size, threshold reshuffle, burn accounting,
# save/restore, and that poker and blackjack both draw from it.

from __future__ import annotations

import argparse
import random

import pytest

from casino.shoe import PIPS, SUITS, Shoe, build_cards


def test_one_deck_is_52_unique_cards_in_casino_format():
    cards = build_cards(1)
    assert len(cards) == 52
    assert len(set(cards)) == 52
    assert "10S" in cards and "AH" in cards and "KD" in cards


def test_each_deck_adds_a_full_copy():
    cards = build_cards(3)
    assert len(cards) == 156
    assert all(cards.count(c) == 3 for c in set(cards))


def test_zero_decks_is_refused():
    with pytest.raises(ValueError):
        build_cards(0)


def test_shoe_defaults_to_one_deck_and_reports_size():
    shoe = Shoe()
    assert shoe.decks == 1
    assert shoe.size == 52
    assert shoe.remaining == 52
    assert len(set(shoe.cards)) == 52


def test_threshold_must_be_a_fraction():
    with pytest.raises(ValueError):
        Shoe(threshold=0)
    with pytest.raises(ValueError):
        Shoe(threshold=1.5)


def test_reshuffles_only_after_the_threshold_is_passed():
    shoe = Shoe(decks=2, threshold=0.5)  # size 104, reshuffle after 52 draws
    shoe.draw_many(52)
    assert shoe.reshuffles == 1 and not shoe.needs_reshuffle()
    shoe.draw()  # the 53rd draw is past the threshold; the next draw rebuilds
    assert shoe.reshuffles == 1
    shoe.draw()
    assert shoe.reshuffles == 2
    assert shoe.uses == 1


def test_a_burn_counts_toward_the_threshold():
    shoe = Shoe(decks=1, threshold=1.0)
    shoe.burn()
    assert shoe.uses == 1
    assert shoe.remaining == 51


def test_draws_never_repeat_within_one_pass_of_a_single_deck():
    shoe = Shoe(decks=1, threshold=1.0)
    drawn = shoe.draw_many(52)
    assert len(set(drawn)) == 52


def test_restore_resumes_the_same_draw_count():
    cards = build_cards(2)
    random.Random(7).shuffle(cards)
    restored = Shoe.from_state(cards, 10, decks=2, threshold=0.8)
    assert restored.uses == 10
    assert restored.remaining == 104
    assert restored.draw() == cards[-1]


def test_seeded_shoes_deal_the_same_order():
    a, b = Shoe(decks=1), Shoe(decks=1)
    a.seed(random.Random(42))
    b.seed(random.Random(42))
    a._rebuild()
    b._rebuild()
    assert a.cards == b.cards


def test_suits_and_pips_are_the_standard_thirteen_and_four():
    assert len(SUITS) == 4 and len(PIPS) == 13


def test_poker_draws_its_cards_from_the_shoe():
    from casino.services.poker import PokerService

    svc = PokerService(argparse.Namespace(databasename="zoid6test", debug=False))
    svc.create_table(table_moniker="shoe-poker", variant_name="holdem", betting_structure="no_limit",
                     small_blind=1, big_blind=2)
    for m in ("bjbed_a", "bjbed_b"):
        svc.join_table("shoe-poker", m, 100)
    svc.start_hand("shoe-poker")
    t = svc._tables["shoe-poker"]
    shoe = svc._decks["shoe-poker"]
    assert isinstance(shoe, Shoe)
    cur = t.current_player
    svc.player_action("shoe-poker", cur, "raise", 6)
    svc.player_action("shoe-poker", t.current_player, "call")
    while t.game_stage != "showdown":
        svc.player_action("shoe-poker", t.current_player, "check")
    # 4 hole cards + 5 board cards + 5 burns (one per street) = 14 draws in this hand.
    assert shoe.uses == 14
    dealt = [c for p in t.players.values() for c in p.hole_cards] + t.community_cards
    assert len(dealt) == len(set(dealt)) == 9


def test_blackjack_creates_its_shoe_from_the_shared_definition():
    from casino.services.game import GameService

    svc = GameService.__new__(GameService)
    cards = svc._create_shoe(decks=2)
    assert len(cards) == 104
    assert sorted(cards) == sorted(build_cards(2))
