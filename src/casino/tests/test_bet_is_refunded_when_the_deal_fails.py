"""A bet whose deal fails is refunded: the bet and its first hand succeed or fail together.

The bet is committed before the hand and cards are created, in separate connections. A failure after the bet
left a bet with no hand, so the next bet looked like the first had not counted. Now a failed deal refunds the
stake, marks the bet refunded, and returns the error.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino.dal import bet as dal_bet
from casino.dal import game as dal_game
from casino.dal import table as dal_table
from casino.services import game as game_mod


pytestmark = pytest.mark.unit


def _service():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    svc._draw_card = lambda table: "2C"
    return svc


def test_a_failed_hand_creation_refunds_the_bet_and_reports_the_error():
    svc = _service()
    refund = MagicMock()
    with patch.object(dal_table, "get_table", return_value={"minimumbet": 1, "maximumbet": 100}), \
         patch.object(svc, "_close_stale_round"), \
         patch.object(dal_game, "get_active_game", return_value={"id": 162}), \
         patch.object(dal_bet, "place_bet", return_value={"id": 164, "amount": 10}), \
         patch.object(dal_game, "create_hand", side_effect=RuntimeError("deal failed")), \
         patch.object(svc, "_refund_bet", refund):
        result = svc.place_bet("blackjack-jam", "jam", 10)
    refund.assert_called_once_with({"id": 164, "amount": 10})
    assert result["success"] is False


def test_a_successful_deal_is_not_refunded():
    svc = _service()
    refund = MagicMock()
    with patch.object(dal_table, "get_table", return_value={"minimumbet": 1, "maximumbet": 100}), \
         patch.object(svc, "_close_stale_round"), \
         patch.object(dal_game, "get_active_game", return_value={"id": 162}), \
         patch.object(dal_bet, "place_bet", return_value={"id": 164, "amount": 10}), \
         patch.object(dal_game, "create_hand", return_value={"id": 9}), \
         patch.object(dal_game, "update_hand_cards"), \
         patch.object(dal_bet, "update_bet_hand_id"), \
         patch.object(dal_bet, "update_bet_currenthand"), \
         patch.object(svc, "_deal_dealer_and_peek", return_value={"natural": False, "checked": False}), \
         patch.object(svc, "_publish_bet"), \
         patch.object(svc, "_refund_bet", refund):
        svc.place_bet("blackjack-jam", "jam", 10)
    refund.assert_not_called()
