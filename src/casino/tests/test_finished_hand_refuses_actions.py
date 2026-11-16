"""A finished hand refuses further actions, and a bet is refused while the player's hand is still open.

A hand is finished when it busted, stood, surrendered, or otherwise acted (ACTED_STATUSES). Hit, stand, double,
split, and surrender on a finished hand are refused with a clear message, not the generic "No hand found". A bet
is refused while the player has a hand in play in the round, so one round does not stack hands.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.dal import game as dal_game
from casino.services import game as game_mod


pytestmark = pytest.mark.unit


def _svc():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    return svc


BUSTED = {"id": 320, "playermoniker": "jam", "cards": ["3D", "3S", "8H", "2C", "9S"], "attrs": {"status": "bust"}}


@pytest.mark.parametrize("action", ["hit", "stand", "double", "split", "surrender"])
def test_an_action_on_a_busted_hand_is_refused_clearly(action):
    svc = _svc()
    with patch.object(dal_game, "get_active_game", return_value={"id": 162}), \
         patch.object(dal_game, "get_player_hands", return_value=[BUSTED]), \
         patch.object(svc, "_round_expired", return_value=False):
        result = getattr(svc, action)("blackjack-jam", "jam")
    assert result.ok is False
    assert result.message == "Your hand is finished."


def test_the_open_hand_refusal_names_the_cards_and_the_way_out():
    svc = _svc()
    open_hand = {"id": 323, "playermoniker": "jam", "cards": ["10H", "JH"], "attrs": {}}
    with patch.object(dal_game, "get_active_game", return_value={"id": 162}), \
         patch.object(dal_game, "get_player_hands", return_value=[open_hand]), \
         patch.object(svc, "_close_stale_round"), \
         patch.object(game_mod.dal_table, "get_table", return_value={"minimumbet": 1, "maximumbet": 100}):
        result = svc.place_bet("blackjack-jam", "jam", 5)
    assert result["success"] is False
    assert "10H JH" in result["message"], "the refusal shows the open hand's cards"
    assert "game hands" in result["message"], "the refusal says how to see the hand"
    assert "game stand" in result["message"], "the refusal says how to finish the hand"


def test_a_bet_is_refused_while_a_hand_is_still_open():
    svc = _svc()
    open_hand = {"id": 323, "playermoniker": "jam", "cards": ["10H", "JH"], "attrs": {}}
    with patch.object(dal_game, "get_active_game", return_value={"id": 162}), \
         patch.object(dal_game, "get_player_hands", return_value=[open_hand]), \
         patch.object(svc, "_close_stale_round"), \
         patch.object(game_mod.dal_table, "get_table", return_value={"minimumbet": 1, "maximumbet": 100}):
        result = svc.place_bet("blackjack-jam", "jam", 5)
    assert result["success"] is False
    assert "still in play" in result["message"]


def test_a_bet_is_allowed_once_every_hand_is_finished():
    svc = _svc()
    with patch.object(dal_game, "get_active_game", return_value={"id": 162}), \
         patch.object(dal_game, "get_player_hands", return_value=[BUSTED]), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(svc, "_close_stale_round"), \
         patch.object(game_mod.dal_table, "get_table", return_value={"minimumbet": 1, "maximumbet": 100}), \
         patch.object(game_mod.dal_bet, "place_bet", side_effect=ValueError("stop after the gate")):
        result = svc.place_bet("blackjack-jam", "jam", 5)
    # The gate let the bet through: the failure is from the bet insert, not from the open-hand refusal.
    assert result["message"] == "stop after the gate"
