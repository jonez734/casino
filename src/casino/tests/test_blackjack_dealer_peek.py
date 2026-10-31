#!/usr/bin/env python3
# casino/tests/test_blackjack_dealer_peek.py
# Dealer peek: when the upcard is an ace or ten, the hole card is checked for a natural right after
# the deal, before any player acts. A natural ends the round at once, so hit, double, split, and
# surrender are never offered. Stubbed: no database.

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino.blackjack.settle import dealer_peek_applies, dealer_peek_natural
from casino.dal import bet as dal_bet
from casino.dal import game as dal_game
from casino.dal import table as dal_table
from casino.services import game as game_mod


def _draws(cards):
    """A _draw_card stub that returns the given cards in order, then 2C forever."""
    queue = list(cards)
    return lambda table_moniker: queue.pop(0) if queue else "2C"


def _service():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    return svc


# ---- the rule ---------------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("upcard,applies", [
    ("AH", True), ("10S", True), ("KD", True), ("QC", True), ("JH", True),
    ("9C", False), ("2H", False), ("7S", False),
])
def test_peek_only_for_ace_or_ten_value_upcard(upcard, applies):
    assert dealer_peek_applies(upcard) is applies


@pytest.mark.unit
def test_peek_natural_is_a_two_card_21():
    assert dealer_peek_natural(["AS", "QC"]) is True
    assert dealer_peek_natural(["KS", "AC"]) is True
    assert dealer_peek_natural(["9S", "7C", "5D"]) is False  # 21 with three cards: not a natural


# ---- place_bet: the deal, the peek, and the settlement ----------------------------------------

@pytest.mark.unit
def test_dealer_natural_settles_the_round_inside_place_bet():
    svc = _service()
    dealer_cards = ["AS", "QC"]  # ace upcard, natural hole card
    game = {"id": 7, "status": "player"}

    settle = MagicMock(return_value={"success": True, "outcomes": [], "dealer_total": 21})
    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(dal_table, "get_table", return_value={"minimumbet": 1, "maximumbet": 100}), \
         patch.object(game_mod.dal_bet, "place_bet", return_value={"id": 5}), \
         patch.object(dal_game, "create_hand", return_value={"id": 9}), \
         patch.object(dal_game, "update_hand_cards"), \
         patch.object(game_mod.dal_bet, "update_bet_hand_id"), \
         patch.object(game_mod.dal_bet, "update_bet_currenthand"), \
         patch.object(svc, "_draw_card", side_effect=_draws(["10H", "8D"])), \
         patch.object(dal_game, "get_or_create_dealer_hand", return_value={"cards": dealer_cards, "attrs": {}}), \
         patch.object(dal_game, "update_dealer_hand_cards"), \
         patch.object(dal_game, "set_dealer_hole_card"), \
         patch.object(dal_game, "reveal_dealer_hole_card") as reveal, \
         patch.object(svc, "settle_game", settle):
        result = svc.place_bet("blackjack-x", "p1", 10)

    assert result["success"] is True
    assert result["dealer_peek"] == {"natural": True, "checked": True}
    reveal.assert_called_once()
    settle.assert_called_once_with("blackjack-x")


@pytest.mark.unit
def test_no_natural_leaves_the_round_open_for_play():
    svc = _service()
    game = {"id": 7, "status": "player"}
    settle = MagicMock()
    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(dal_table, "get_table", return_value={"minimumbet": 1, "maximumbet": 100}), \
         patch.object(game_mod.dal_bet, "place_bet", return_value={"id": 5}), \
         patch.object(dal_game, "create_hand", return_value={"id": 9}), \
         patch.object(dal_game, "update_hand_cards"), \
         patch.object(game_mod.dal_bet, "update_bet_hand_id"), \
         patch.object(game_mod.dal_bet, "update_bet_currenthand"), \
         patch.object(svc, "_draw_card", side_effect=_draws(["10H", "8D"])), \
         patch.object(dal_game, "get_or_create_dealer_hand", return_value={"cards": ["KS", "9C"], "attrs": {}}), \
         patch.object(dal_game, "update_dealer_hand_cards"), \
         patch.object(dal_game, "set_dealer_hole_card"), \
         patch.object(dal_game, "reveal_dealer_hole_card") as reveal, \
         patch.object(svc, "settle_game", settle):
        result = svc.place_bet("blackjack-x", "p1", 10)

    assert result["dealer_peek"] == {"natural": False, "checked": True}
    reveal.assert_not_called()
    settle.assert_not_called()


@pytest.mark.unit
def test_no_peek_when_the_upcard_cannot_make_a_natural():
    svc = _service()
    game = {"id": 7, "status": "player"}
    settle = MagicMock()
    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(dal_table, "get_table", return_value={"minimumbet": 1, "maximumbet": 100}), \
         patch.object(game_mod.dal_bet, "place_bet", return_value={"id": 5}), \
         patch.object(dal_game, "create_hand", return_value={"id": 9}), \
         patch.object(dal_game, "update_hand_cards"), \
         patch.object(game_mod.dal_bet, "update_bet_hand_id"), \
         patch.object(game_mod.dal_bet, "update_bet_currenthand"), \
         patch.object(svc, "_draw_card", side_effect=_draws(["10H", "8D"])), \
         patch.object(dal_game, "get_or_create_dealer_hand", return_value={"cards": ["6S", "9C"], "attrs": {}}), \
         patch.object(dal_game, "update_dealer_hand_cards"), \
         patch.object(dal_game, "set_dealer_hole_card"), \
         patch.object(dal_game, "reveal_dealer_hole_card") as reveal, \
         patch.object(svc, "settle_game", settle):
        result = svc.place_bet("blackjack-x", "p1", 10)

    assert result["dealer_peek"] == {"natural": False, "checked": False}
    reveal.assert_not_called()
    settle.assert_not_called()


@pytest.mark.unit
def test_actions_are_refused_once_a_dealer_natural_has_settled_the_round():
    # The round is settled, so get_active_game (which excludes settled rounds) finds nothing and
    # every action fails with "No active game" rather than being offered.
    svc = _service()
    with patch.object(dal_game, "get_active_game", return_value=None):
        assert svc.hit("blackjack-x", "p1")["success"] is False
        assert svc.stand("blackjack-x", "p1")["success"] is False
        assert svc.double("blackjack-x", "p1")["success"] is False
        assert svc.split("blackjack-x", "p1")["success"] is False
        assert svc.surrender("blackjack-x", "p1")["success"] is False


@pytest.mark.unit
def test_insurance_pays_2_to_1_when_the_dealer_has_a_natural():
    # Insurance is settled in settle_game: a dealer natural pays insurance 2:1.
    from casino.services import game as g

    svc = _service()
    game = {"id": 7, "status": "player", "tablemoniker": "blackjack-x", "kind": "blackjack"}
    dealer = {"id": 1, "playermoniker": None, "cards": ["AS", "QC"], "attrs": {"is_dealer": True}}
    hand = {"id": 10, "playermoniker": "jam", "cards": ["10H", "9D"], "attrs": {"status": "standing"}}
    bet = {"id": 100, "amount": Decimal("10"), "status": "pending"}
    settle_insurance = MagicMock()
    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(dal_game, "get_game_hands", return_value=[hand, dealer]), \
         patch.object(dal_game, "update_game_status"), \
         patch.object(dal_game, "update_game_attrs"), \
         patch.object(dal_table, "get_table", return_value={"attrs": {}}), \
         patch.object(dal_bet, "get_bet_for_hand", return_value=bet), \
         patch.object(dal_bet, "get_insurance", return_value=Decimal("5")), \
         patch.object(dal_bet, "settle_bet"), \
         patch.object(dal_bet, "settle_insurance", settle_insurance), \
         patch.object(g.dal_player, "increment_stat"), \
         patch.object(svc, "_run_dealer_turn", return_value=["AS", "QC"]):
        svc.settle_game("blackjack-x")

    settle_insurance.assert_called_once()
    args = settle_insurance.call_args.args
    assert args[2] is True and args[3] == 10  # insurance of 5 pays 2:1 = 10
