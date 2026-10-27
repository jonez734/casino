#!/usr/bin/env python3
# casino/tests/test_surrender_decimal_bet.py
# Regression: the bet amount comes back from the database as Decimal. Multiplying a Decimal by the
# float surrender multiplier raised TypeError, so every surrender ended in service_error. Stubbed:
# no database.

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.dal import bet as dal_bet
from casino.dal import game as dal_game
from casino.dal import table as dal_table
from casino.services import game as game_mod


def _service():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    return svc


@pytest.mark.unit
def test_surrender_accepts_a_decimal_bet_amount():
    svc = _service()
    game = {"id": 7, "table_moniker": "blackjack-x"}
    hand = {"id": 9, "cards": ["AH", "KD"], "attrs": {}}
    bet = {"id": 3, "amount": Decimal("100")}

    settled = {}

    def fake_settle(args, bet_id, won, amount, pool=None):
        settled["amount"] = amount

    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(dal_game, "get_player_hand", return_value=hand), \
         patch.object(dal_game, "update_hand_attrs"), \
         patch.object(dal_game, "update_game_attrs"), \
         patch.object(dal_table, "get_table", return_value={"attrs": {}}), \
         patch.object(dal_bet, "get_bet_for_hand", return_value=bet), \
         patch.object(dal_bet, "settle_bet", side_effect=fake_settle), \
         patch.object(game_mod, "get_surrender_multiplier", return_value=0.5), \
         patch.object(svc, "_round_expired", return_value=False):
        result = svc.surrender("blackjack-x", "player")

    assert result.get("success") is True, result
    assert settled["amount"] == 50
    assert result["returned"] == 50
    assert result["forfeited"] == 50


def _state_with_table(attrs):
    svc = _service()
    table = {"moniker": "blackjack-x", "attrs": attrs, "type": "blackjack"}
    game = {"id": 7, "status": "player", "table_moniker": "blackjack-x"}
    hand = {"id": 9, "cards": ["AH", "KD"], "attrs": {"status": "playing"}}
    with patch.object(dal_table, "get_table", return_value=table), \
         patch.object(dal_game, "get_current_game", return_value=game), \
         patch.object(dal_game, "get_player_hands", return_value=[hand]), \
         patch.object(dal_game, "get_dealer_hand", return_value=None), \
         patch.object(dal_bet, "get_bet_for_hand", return_value={"amount": Decimal("50")}), \
         patch.object(svc, "_is_dealer_showing_ace", return_value=False, create=True), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(svc, "_draw_card", return_value="2C", create=True), \
         patch.object(dal_game, "create_dealer_hand"), \
         patch.object(dal_game, "update_dealer_hand_cards"), \
         patch.object(dal_game, "set_dealer_hole_card", create=True), \
         patch.object(dal_bet, "get_insurance", return_value=None, create=True), \
         patch.object(svc, "_hide_hole_card", return_value=[], create=True), \
         patch.object(dal_game, "get_game_hands", return_value=[]):
        return svc.get_game_state("blackjack-x", "player")


@pytest.mark.unit
def test_game_state_hides_surrender_when_the_table_disables_it():
    state = _state_with_table({"surrender": False})
    hands = state.get("hands", [])
    assert hands, state
    assert hands[0]["can_surrender"] is False


@pytest.mark.unit
def test_game_state_offers_surrender_by_default():
    state = _state_with_table({})
    hands = state.get("hands", [])
    assert hands, state
    assert hands[0]["can_surrender"] is True
