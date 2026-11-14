"""Typed payloads for blackjack's settlement and state (slice 3c-2). Round trips must be exact.

These are casino's own types, not the seam's ActionResult: a payload is data, not a refusal. Each
type's to_dict returns the dict the client already receives, so a conversion changes no wire output.
"""

import pytest

from casino.api.payloads import GameState, PlacedBet, RoundSettlement

pytestmark = pytest.mark.unit


SETTLEMENT = {
    "outcomes": [
        {"hand_id": 10, "player": "jam", "result": "win", "bet": 10, "net": 10, "payout": 20},
        {"hand_id": 11, "player": "jam", "result": "loss", "bet": 10, "net": -10, "payout": 0},
    ],
    "dealer_total": 17,
    "dealer_cards": ["10H", "7D"],
}


def test_round_settlement_round_trips_exactly():
    assert RoundSettlement.from_dict(SETTLEMENT).to_dict() == SETTLEMENT


def test_round_settlement_exposes_its_outcomes():
    s = RoundSettlement.from_dict(SETTLEMENT)
    assert [o.hand_id for o in s.outcomes] == [10, 11]
    assert s.outcomes[1].net == -10


def test_round_settlement_without_outcomes_is_empty():
    s = RoundSettlement.from_dict({"dealer_total": 0})
    assert s.outcomes == () and s.has_outcomes is False


STATE = {
    "table_moniker": "t1",
    "game_id": 9,
    "phase": "player",
    "hands": [],
    "seats": [],
    "player_hand": ["10H", "7D"],
    "player_total": 17,
    "dealer_hand": ["10S"],
    "dealer_total": 10,
    "insurance_available": False,
    "insurance_taken": 0,
}


def test_game_state_round_trips_exactly_including_unknown_keys():
    # The state carries more keys than the typed fields; they must come back unchanged.
    state = dict(STATE, some_future_key=[1, 2])
    assert GameState.from_dict(state).to_dict() == state


def test_game_state_exposes_the_fields_the_handler_reads():
    g = GameState.from_dict(STATE)
    assert g.phase == "player" and g.table_moniker == "t1"


def test_placed_bet_round_trips_exactly():
    placed = {
        "success": True,
        "bet_id": 5,
        "hand_id": 3,
        "cards": ["10H", "7D"],
        "total": 17,
        "dealer_peek": None,
        "message": "Bet 10 placed",
    }
    assert PlacedBet.from_dict(placed).to_dict() == placed


def test_take_settled_round_returns_a_typed_settlement_or_none():
    from unittest.mock import patch

    from casino.services import game as game_mod

    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.__dict__["_last_settled"] = {"t1": dict(SETTLEMENT)}
    got = svc.take_settled_round("t1")
    assert isinstance(got, RoundSettlement)
    assert got.to_dict() == SETTLEMENT
    assert svc.take_settled_round("t1") is None


def test_settle_game_with_no_active_game_returns_an_empty_settlement():
    from unittest.mock import patch

    from casino.services import game as game_mod

    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = None
    svc._pool = None
    with patch.object(game_mod.dal_game, "get_active_game", return_value=None):
        got = svc.settle_game("t1")
    assert isinstance(got, RoundSettlement)
    assert got.has_outcomes is False and got.outcomes == ()



def test_place_bet_success_is_a_typed_placed_bet():
    from unittest.mock import patch

    from casino.services import game as game_mod

    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = None
    svc._pool = None
    game = {"id": 9, "status": "betting"}
    with patch.object(game_mod.dal_table, "get_table", return_value={"minimumbet": 1, "maximumbet": 100}), \
         patch.object(game_mod.dal_game, "get_active_game", return_value=game), \
         patch.object(game_mod.dal_bet, "place_bet", return_value={"id": 5}), \
         patch.object(game_mod.dal_game, "create_hand", return_value={"id": 3}), \
         patch.object(game_mod.dal_game, "update_hand_cards"), \
         patch.object(game_mod.dal_bet, "update_bet_hand_id"), \
         patch.object(game_mod.dal_bet, "update_bet_currenthand"), \
         patch.object(svc, "_draw_card", side_effect=["10H", "7D"]), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(svc, "_deal_dealer_and_peek", return_value={"natural": False, "checked": True}):
        got = svc.place_bet("t1", "alice", 10)
    assert isinstance(got, PlacedBet)
    assert got.bet_id == 5 and got.hand_id == 3 and got.cards == ["10H", "7D"]
    assert got.to_dict()["dealer_peek"] == {"natural": False, "checked": True}



def test_get_game_state_waiting_is_a_typed_game_state():
    from unittest.mock import patch

    from casino.services import game as game_mod

    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = None
    svc._pool = None
    with patch.object(game_mod.dal_table, "get_table", return_value={"attrs": {}}), \
         patch.object(game_mod.dal_game, "get_current_game", return_value=None):
        got = svc.get_game_state("t1", "bob")
    assert isinstance(got, GameState)
    assert got.phase == "waiting" and got.table_moniker == "t1"
    assert got.to_dict()["hands"] == []
