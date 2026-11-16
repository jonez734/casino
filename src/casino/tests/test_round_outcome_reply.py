#!/usr/bin/env python3
# casino/tests/test_round_outcome_reply.py
# A settled round must tell the player what happened: each hand's outcome, its bet, and the net change.
# Before this, settle_game computed the outcomes but returned only the dealer total, so the player saw
# no result and no money change. Stubbed: no database.

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
def test_settle_game_returns_each_hands_outcome_and_net():
    svc = _service()
    game = {"id": 7, "status": "player", "tablemoniker": "blackjack-x"}
    dealer = {"id": 1, "playermoniker": None, "cards": ["10H", "7D"], "attrs": {"is_dealer": True}}
    hands = [
        {"id": 10, "playermoniker": "jam", "cards": ["10S", "9C"], "attrs": {"status": "standing"}},
        {"id": 11, "playermoniker": "jam", "cards": ["10D", "5C"], "attrs": {"status": "standing"}},
    ]
    bets = {
        10: {"id": 100, "amount": Decimal("10"), "status": "pending"},
        11: {"id": 101, "amount": Decimal("10"), "status": "pending"},
    }

    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(dal_game, "get_game_hands", return_value=hands + [dealer]), \
         patch.object(dal_game, "get_dealer_hand", return_value=dealer), \
         patch.object(dal_game, "update_game_status"), \
         patch.object(dal_game, "update_game_attrs"), \
         patch.object(dal_game, "get_dealer_hole_card", return_value=None), \
         patch.object(dal_game, "reveal_dealer_hole_card", return_value=None), \
         patch.object(dal_table, "get_table", return_value={"attrs": {}}), \
         patch.object(dal_bet, "get_bet_for_hand", side_effect=lambda a, hid, pool=None: bets.get(hid)), \
         patch.object(dal_bet, "get_insurance", return_value=0), \
         patch.object(dal_bet, "settle_bet"), \
         patch.object(dal_game, "merge_hand_result"), \
         patch.object(game_mod.dal_player, "increment_stat"), \
         patch.object(svc, "_run_dealer_turn", return_value=["10H", "7D"]):
        result = svc.settle_game("blackjack-x")

    assert result.has_outcomes, "settle_game must return the per-hand outcomes"
    outcomes = result.outcomes
    assert [o.hand_id for o in outcomes] == [10, 11]
    # dealer 17. 19 beats 17 (win, +10). 15 loses to 17 (loss, -10).
    assert outcomes[0].result == "win" and outcomes[0].net == 10
    assert outcomes[1].result == "loss" and outcomes[1].net == -10
    assert all(o.bet == 10 for o in outcomes)
    assert result.dealer_total == 17


@pytest.mark.unit
def test_stand_reply_carries_the_settled_outcomes():
    # The stand reply must include the round outcome so the player is told the result and the money.
    import inspect
    from casino.api import handler as handler_mod

    src = inspect.getsource(handler_mod.GameServiceHandler._handle_game_action)
    assert 'settled = _settlement_dict(self.game_service.settle_game(table_moniker))' in src, (
        "stand must keep the settlement result"
    )
    assert '"round_settled"' in src, "the reply must carry a round_settled message"


@pytest.mark.unit
def test_client_shows_the_round_result_and_money_change():
    # When a round settles, the player must see each hand's outcome, the bet, and the net change.
    import inspect
    from casino.client import casino_client as cc

    src = inspect.getsource(cc.CasinoClient.display_game_state)
    assert "round_settled" in src, "the client must show the settled round"
    assert "net" in src and "outcome" in src, "the client must show each outcome and the net change"


def test_the_broadcast_round_net_is_the_sum_of_the_outcomes():
    # A table broadcast (moniker None) must carry the round's total, the same as a reply does for a player.
    from casino.api import handler as handler_mod

    settled = {
        "outcomes": [
            {"player": "alice", "net": 10},
            {"player": "bob", "net": -4},
        ],
        "dealer_total": 20,
        "dealer_cards": ["JC", "4H", "6S"],
    }
    assert handler_mod._round_settled_payload(settled, None)["net"] == 6


def test_a_player_reply_still_carries_that_players_net():
    from casino.api import handler as handler_mod

    settled = {
        "outcomes": [
            {"player": "alice", "net": 10},
            {"player": "bob", "net": -4},
        ],
        "dealer_total": 20,
        "dealer_cards": ["JC", "4H", "6S"],
    }
    assert handler_mod._round_settled_payload(settled, "bob")["net"] == -4
