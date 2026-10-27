#!/usr/bin/env python3
# casino/tests/test_seats.py
# Phase 4 slice 1: the seat-module registry. Each game type's capacity comes from one place.

import pytest

from casino import seats


@pytest.mark.unit
@pytest.mark.parametrize(
    "game, lo, hi",
    [
        ("blackjack", 1, 7),
        ("poker", 2, 10),
        ("slots", 0, 1),
        ("yahtzee", 1, 6),
        ("tictactoe", 2, 2),
    ],
)
def test_seat_counts_match_the_design(game, lo, hi):
    module = seats.seat_module(game)
    assert module is not None
    assert (module.min_players, module.max_players) == (lo, hi)


@pytest.mark.unit
def test_unknown_game_has_no_seat_module():
    assert seats.seat_module("craps") is None


@pytest.mark.unit
def test_game_types_lists_every_registered_game_sorted():
    assert seats.game_types() == ("blackjack", "poker", "slots", "tictactoe", "yahtzee")


@pytest.mark.unit
def test_has_room_stops_at_max_players():
    assert seats.has_room("blackjack", 6) is True
    assert seats.has_room("blackjack", 7) is False
    assert seats.has_room("slots", 0) is True
    assert seats.has_room("slots", 1) is False


@pytest.mark.unit
def test_has_room_is_true_for_a_game_with_no_rule():
    assert seats.has_room("craps", 99) is True


@pytest.mark.unit
def test_seat_module_rejects_min_above_max():
    with pytest.raises(ValueError):
        seats.SeatModule("x", min_players=5, max_players=2)


@pytest.mark.unit
def test_seat_module_rejects_negative_counts():
    with pytest.raises(ValueError):
        seats.SeatModule("x", min_players=-1, max_players=2)


@pytest.mark.unit
def test_seat_module_is_immutable():
    module = seats.seat_module("poker")
    with pytest.raises(Exception):
        module.max_players = 99  # frozen dataclass
