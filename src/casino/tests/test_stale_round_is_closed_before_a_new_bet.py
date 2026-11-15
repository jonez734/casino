"""A bet on a table whose open round has old hands closes that round first, then deals a fresh one.

Before this, a bet reused whatever round was open. Old hands the player never acted on stayed in it, and
the next stand settled them too, so an earlier 14 and an earlier 27 were paid on this round's stand.

Rule (agreed): before the new deal, every hand in the stale round the player never acted on is refunded in
full (the round clock's ``remove`` path); the hands that were played out are settled. Then the new bet deals.
Tests use stand-ins for the database; no connection is opened.
"""

from types import SimpleNamespace

import pytest

from casino.services import game as game_mod


pytestmark = pytest.mark.unit


def test_a_stale_round_is_refunded_for_unplayed_hands_and_settled_for_played_ones(monkeypatch):
    from casino.dal import bet as dal_bet
    from casino.dal import game as dal_game

    service = game_mod.GameService.__new__(game_mod.GameService)
    service.args = SimpleNamespace()
    service._pool = None

    stale_hands = [
        {"id": 312, "playermoniker": "jam", "cards": ["9H", "3C", "2D", "5D"], "attrs": {"status": "standing"}},
        {"id": 314, "playermoniker": "jam", "cards": ["7D", "QC", "10D"], "attrs": {"status": "bust"}},
        {"id": 315, "playermoniker": "jam", "cards": ["6H", "8D"], "attrs": {}},
    ]
    bets = {312: {"id": 1, "amount": 5, "status": "pending"},
            314: {"id": 2, "amount": 1, "status": "pending"},
            315: {"id": 3, "amount": 5, "status": "pending"}}
    refunded, settled_flags = [], []

    monkeypatch.setattr(dal_game, "get_active_game", lambda *a, **k: {"id": 159, "tablemoniker": "t"})
    monkeypatch.setattr(dal_game, "get_game_hands", lambda *a, **k: list(stale_hands))
    monkeypatch.setattr(dal_bet, "get_bet_for_hand", lambda args, hid, **k: bets[hid])
    monkeypatch.setattr(dal_bet, "settle_bet", lambda args, bid, won, amount, **k: refunded.append((bid, won, amount)))
    monkeypatch.setattr(dal_game, "update_hand_status", lambda args, hid, status, **k: settled_flags.append((hid, status)))
    settled_tables = []
    service.settle_game = lambda table: settled_tables.append(table)
    from casino.dal import table as dal_table
    monkeypatch.setattr(dal_table, "seated_monikers", lambda *a, **k: [])  # jam has left: the round is stale

    service._close_stale_round("t")

    # Unplayed hand (315, no status): refunded in full and marked standup. The played hands are left for settle.
    assert (3, True, 5) in refunded
    assert (1, True, 5) not in refunded and (2, True, 1) not in refunded
    assert settled_flags == [(315, "standup")]
    assert settled_tables == ["t"], "the played hands are then settled"


def test_a_round_still_shared_by_seated_players_is_left_open(monkeypatch):
    from casino.dal import bet as dal_bet
    from casino.dal import game as dal_game
    from casino.dal import table as dal_table

    service = game_mod.GameService.__new__(game_mod.GameService)
    service.args = SimpleNamespace()
    service._pool = None
    hands = [{"id": 1, "playermoniker": "jam", "cards": ["9H", "3C"], "attrs": {}},
             {"id": 2, "playermoniker": "bob", "cards": ["KD", "2S"], "attrs": {}}]
    refunded, settled_tables = [], []
    monkeypatch.setattr(dal_game, "get_active_game", lambda *a, **k: {"id": 7})
    monkeypatch.setattr(dal_game, "get_game_hands", lambda *a, **k: hands)
    monkeypatch.setattr(dal_table, "seated_monikers", lambda *a, **k: ["jam", "bob"])
    monkeypatch.setattr(dal_bet, "settle_bet", lambda *a, **k: refunded.append(a))
    service.settle_game = lambda table: settled_tables.append(table)

    service._close_stale_round("t")

    assert refunded == [] and settled_tables == [], "both seats are still at the table: nothing is closed"
