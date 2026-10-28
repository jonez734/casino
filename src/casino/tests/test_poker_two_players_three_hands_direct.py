# casino/tests/test_poker_two_players_three_hands_direct.py
# Two players (bjbed_a, bjbed_b) play 3 scripted hands of holdem through PokerService.
#
# Direct, in-process: no bed daemon, no websocket. Chips live in memory (PokerService._tables),
# so the table math is checked in memory. Bank balances are read from the database before and
# after the session. Poker does not settle to the DB yet (see casino/TODO.md "Poker stats
# (deferred)"), so the balances are expected to be unchanged; any movement is reported.
#
# Opt-in: runs only when CASINO_TEST_DIRECT_DB is set to the database name (e.g. zoid6test).
# Refuses the live database "zoid6".

from __future__ import annotations

import argparse
import os
import sys

import pytest

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")

from casino.dal import player as dal_player
from casino.services.poker import PokerService

PLAYERS = ("bjbed_a", "bjbed_b")
NUM_HANDS = 10
BUY_IN = 500  # headroom so scripted bets over 10 hands cannot bust a seat
TOTAL_CHIPS = BUY_IN * len(PLAYERS)
LIVE_DATABASES = frozenset({"zoid6"})
TABLE = "poker-direct-2p"

TEST_DB = os.environ.get("CASINO_TEST_DIRECT_DB", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not TEST_DB, reason="set CASINO_TEST_DIRECT_DB=zoid6test to run"),
]


def _args() -> argparse.Namespace:
    if TEST_DB in LIVE_DATABASES:
        raise RuntimeError(f"refusing live database {TEST_DB!r}")
    return argparse.Namespace(databasename=TEST_DB, debug=False)


def _balances(args) -> dict:
    return {m: dal_player.get_player_balance(args, m) for m in PLAYERS}


def _seat_players(svc: PokerService) -> None:
    created = svc.create_table(
        table_moniker=TABLE,
        variant_name="holdem",
        betting_structure="no_limit",
        small_blind=1,
        big_blind=2,
    )
    assert created["success"], created
    for m in PLAYERS:
        joined = svc.join_table(TABLE, m, BUY_IN)
        assert joined["success"], joined


def _chips(svc: PokerService) -> dict:
    table = svc._tables[TABLE]
    return {m: table.players[m].credits for m in PLAYERS}


def _act(svc, moniker, action, amount=0):
    res = svc.player_action(TABLE, moniker, action, amount)
    assert res.get("success"), f"{moniker} {action} {amount}: {res}"
    return res


def _current(svc) -> str:
    return svc._tables[TABLE].current_player


def _other(m: str) -> str:
    return PLAYERS[1] if m == PLAYERS[0] else PLAYERS[0]


def _street_check_through(svc, first_to_act: str, streets: int) -> None:
    """Check around on each remaining street until the hand reaches showdown."""
    for _ in range(streets):
        # Postflop action starts left of the dealer; with two players the non-button acts first.
        # Let whoever is named current act, checking every turn.
        for _ in range(2):
            cur = _current(svc)
            if cur is None:
                break
            _act(svc, cur, "check")


def _play_hand_1(svc) -> dict:
    """Preflop raise, call; then check through the streets to showdown."""
    t = svc._tables[TABLE]
    first = _current(svc)
    _act(svc, first, "raise", 6)
    _act(svc, _current(svc), "call")
    # Remaining streets: check each turn until the hand ends.
    while t.game_stage != "showdown" and _current(svc) is not None:
        _act(svc, _current(svc), "check")
    return {"stage": t.game_stage, "pot": t.pot}


def _play_hand_2(svc) -> dict:
    """Preflop raise, then fold so the other seat takes the pot without a showdown."""
    t = svc._tables[TABLE]
    first = _current(svc)
    _act(svc, first, "raise", 6)
    _act(svc, _current(svc), "fold")
    return {"stage": t.game_stage, "pot": t.pot}


def _play_hand_3(svc) -> dict:
    """Check/check preflop, then bet/call on each street to showdown."""
    t = svc._tables[TABLE]
    # Preflop: the first actor already matches the big blind (calls for $0), then the other seat
    # completes the small blind by calling.
    _act(svc, _current(svc), "call")
    _act(svc, _current(svc), "call")
    # Postflop, each street: the first actor bets, the other calls, until showdown.
    while t.game_stage != "showdown" and _current(svc) is not None:
        _act(svc, _current(svc), "bet", 4)
        _act(svc, _current(svc), "call")
    return {"stage": t.game_stage, "pot": t.pot}


@pytest.mark.integration
def test_two_players_three_hands_direct():
    args = _args()
    before = _balances(args)
    print(f"\n[db={TEST_DB}] balances before: {before}")

    svc = PokerService(args)
    _seat_players(svc)
    t = svc._tables[TABLE]
    assert _chips(svc) == {m: BUY_IN for m in PLAYERS}

    plays = (_play_hand_1, _play_hand_2, _play_hand_3)
    results = []
    for n in range(1, NUM_HANDS + 1):
        play = plays[(n - 1) % len(plays)]
        started = svc.start_hand(TABLE)
        assert started["success"], started
        outcome = play(svc)
        chips = _chips(svc)
        total = sum(chips.values())
        print(f"hand {n} ({play.__name__}): stage={outcome['stage']} chips={chips} total={total}")
        assert total == TOTAL_CHIPS, f"hand {n} chip total {total} != {TOTAL_CHIPS}"
        assert t.pot == 0, f"hand {n} pot not awarded: {t.pot}"
        assert all(c >= 0 for c in chips.values()), f"hand {n} negative chips: {chips}"
        results.append((n, outcome["stage"], chips))
    assert len(results) == NUM_HANDS

    after = _balances(args)
    print(f"balances after: {after}")
    print(f"balance delta: { {m: after[m] - before[m] for m in PLAYERS} }")

    # Poker does not settle to the DB yet: balances should not move.
    assert after == before, f"bank balances moved unexpectedly: {before} -> {after}"
