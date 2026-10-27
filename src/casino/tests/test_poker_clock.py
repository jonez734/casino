#!/usr/bin/env python3
# casino/tests/test_poker_clock.py
# Poker's per-seat play clock (Phase 1b): the clock belongs to the seat whose turn it is, expiry
# applies to that seat only, bots are clocked the same as humans, and a late action is refused, not applied.
# Pure in-memory tests: no database, no daemon.

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from casino.services import poker_clock as pc
from casino.services import poker as poker_mod

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _seat(moniker, is_bot=False, current_bet=0, credits=500):
    return poker_mod.PokerPlayer(moniker=moniker, seat=1, current_bet=current_bet,
                                 credits=credits, is_bot=is_bot)


@pytest.mark.unit
def test_clock_is_off_at_zero_seconds():
    assert pc.deadline_for(0, now=NOW) is None


@pytest.mark.unit
def test_expires_at_the_deadline_not_before():
    deadline = pc.deadline_for(20, now=NOW)
    assert pc.is_expired(deadline, now=NOW + timedelta(seconds=19)) is False
    assert pc.is_expired(deadline, now=NOW + timedelta(seconds=20)) is True


@pytest.mark.unit
def test_bots_are_clocked_like_humans():
    # A bot that camps on its turn must not hold the table past the deadline.
    assert pc.clocked(_seat("botty", is_bot=True)) is True
    assert pc.clocked(_seat("alice")) is True


@pytest.mark.unit
def test_unknown_penalty_falls_back_to_skip():
    assert pc.penalty_for("bogus") == "skip"
    assert pc.penalty_for("remove") == "remove"


@pytest.mark.unit
def test_skip_checks_when_nothing_is_owed():
    table = SimpleNamespace(clock_penalty="skip")
    seat = _seat("alice")
    out = pc.apply_expiry(table, seat, facing_bet=False)
    assert out == {"penalty": "skip", "action": "check", "seat": "alice"}
    assert seat.has_acted is True and seat.has_folded is False


@pytest.mark.unit
def test_skip_folds_when_facing_a_bet_and_never_bets_for_the_player():
    table = SimpleNamespace(clock_penalty="skip")
    seat = _seat("alice")
    out = pc.apply_expiry(table, seat, facing_bet=True)
    assert out["action"] == "fold"
    assert seat.has_folded is True


@pytest.mark.unit
def test_remove_folds_the_seat_out_even_when_it_could_check():
    table = SimpleNamespace(clock_penalty="remove")
    seat = _seat("alice")
    out = pc.apply_expiry(table, seat, facing_bet=False)
    assert out["action"] == "fold" and out["penalty"] == "remove"
    assert seat.has_folded is True


def _table(turn_seconds=20, penalty="skip"):
    svc = poker_mod.PokerService(args=SimpleNamespace())
    svc._tables = {}
    table = poker_mod.PokerTableState(
        moniker="p1", variant=SimpleNamespace(), betting_structure=SimpleNamespace(),
        small_blind=1, big_blind=2, min_buy_in=100, max_buy_in=1000, min_players=2, max_players=6,
        turn_seconds=turn_seconds, clock_penalty=penalty,
    )
    table.players = {"alice": _seat("alice"), "bob": _seat("bob")}
    svc._tables["p1"] = table
    return svc, table


@pytest.mark.unit
def test_turn_change_sets_a_deadline_for_the_new_human_seat():
    svc, table = _table(turn_seconds=20)
    svc._set_turn(table, "alice")
    assert table.current_player == "alice"
    assert table.turn_deadline is not None


@pytest.mark.unit
def test_turn_to_a_bot_starts_the_clock():
    svc, table = _table(turn_seconds=20)
    table.players["alice"].is_bot = True
    svc._set_turn(table, "alice")
    assert table.turn_deadline is not None


@pytest.mark.unit
def test_expired_seat_cannot_act_late_and_the_turn_passes():
    svc, table = _table(turn_seconds=20, penalty="remove")
    table.players["carol"] = _seat("carol")
    table.players["carol"].seat = 3
    svc._set_turn(table, "alice")
    table.turn_deadline = NOW - timedelta(seconds=1)
    out = svc.player_action("p1", "alice", "check")
    assert out["success"] is False
    assert out["message"] == "Your turn clock expired"
    assert table.players["alice"].has_folded is True
    assert table.current_player == "bob"


@pytest.mark.unit
def test_expiry_that_leaves_one_seat_ends_the_hand_and_pays_it():
    svc, table = _table(turn_seconds=20, penalty="remove")
    table.pot = 40
    svc._set_turn(table, "alice")
    table.turn_deadline = NOW - timedelta(seconds=1)
    out = svc.player_action("p1", "alice", "check")
    assert out["expired"]["winner"] == "bob"
    assert table.players["bob"].credits == 500 + 40
    assert table.pot == 0 and table.game_stage == "showdown"


@pytest.mark.unit
def test_expiry_touches_only_the_expired_seat():
    svc, table = _table(turn_seconds=20, penalty="remove")
    svc._set_turn(table, "alice")
    table.turn_deadline = NOW - timedelta(seconds=1)
    svc.player_action("p1", "alice", "check")
    assert table.players["bob"].has_folded is False


@pytest.mark.unit
def test_action_inside_the_clock_is_not_affected():
    svc, table = _table(turn_seconds=60)
    svc._set_turn(table, "alice")
    assert svc._enforce_turn_clock(table) is None
    assert table.players["alice"].has_folded is False
