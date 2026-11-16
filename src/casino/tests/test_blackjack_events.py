"""Blackjack publishes its round progress as seam events (slice 4). Nothing reads them yet.

GameService owns one bbsengine6.seam Domain. A bet, a card, a settled hand and an expired round each
emit one event into it. Publishing is additive: no reply or state changes.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.services import game as game_mod

pytestmark = pytest.mark.unit


def _service():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    svc.__dict__["_last_settled"] = {}
    from bbsengine6.seam.domain import Domain
    from casino.services.events import register_kinds

    svc.domain = Domain("casino")
    register_kinds(svc.domain)
    svc._sub = svc.domain.subscribe(debug=False)
    return svc


def _kinds(svc):
    return [e.kind for e in svc.domain.read(svc._sub)]


def test_the_domain_knows_the_blackjack_kinds():
    from bbsengine6.seam.events import Event

    svc = _service()
    for kind in ("bet_placed", "card_dealt", "hand_settled", "round_expired"):
        svc.domain.emit(Event(kind, "t1", None, {}))
    assert len(svc.domain.read(svc._sub)) == 4


def test_a_drawn_card_emits_card_dealt():
    # The draw knows the card and the table, not the hand it goes to, so the event carries the card only.
    svc = _service()
    svc._publish_card("t1", "10H")
    [e] = svc.domain.read(svc._sub)
    assert e.kind == "card_dealt" and e.scope == "t1" and e.moniker is None
    assert e.payload == {"card": "10H"}


def test_a_placed_bet_emits_bet_placed():
    svc = _service()
    svc._publish_bet("t1", "bob", 10)
    [e] = svc.domain.read(svc._sub)
    assert e.kind == "bet_placed" and e.payload == {"amount": 10}


def test_a_settled_hand_emits_hand_settled_per_outcome():
    svc = _service()
    svc._publish_settled("t1", [
        {"hand_id": 10, "player": "bob", "result": "win", "net": 10},
        {"hand_id": 11, "player": "bob", "result": "loss", "net": -10},
    ])
    kinds = [(e.kind, e.payload["hand_id"]) for e in svc.domain.read(svc._sub)]
    assert kinds == [("hand_settled", 10), ("hand_settled", 11)]


def test_an_expired_round_emits_round_expired():
    svc = _service()
    svc._publish_expired("t1")
    [e] = svc.domain.read(svc._sub)
    assert e.kind == "round_expired" and e.scope == "t1"


def test_settling_a_round_publishes_each_outcome_from_the_real_settlement():
    from casino.tests.test_round_outcome_reply import _service as _settle_service

    svc = _settle_service()
    svc.domain = None  # a service built without __init__: the domain is made on first publish
    svc.__dict__.pop("domain", None)
    game = {"id": 7, "status": "player", "tablemoniker": "blackjack-x"}
    dealer = {"id": 1, "playermoniker": None, "cards": ["10H", "7D"], "attrs": {"is_dealer": True}}
    hands = [
        {"id": 10, "playermoniker": "jam", "cards": ["10S", "9C"], "attrs": {"status": "standing"}},
        {"id": 11, "playermoniker": "jam", "cards": ["10D", "5C"], "attrs": {"status": "standing"}},
    ]
    bets = {10: {"id": 100, "amount": Decimal("10"), "status": "pending"},
            11: {"id": 101, "amount": Decimal("10"), "status": "pending"}}
    from bbsengine6.seam.domain import Domain
    from casino.services import game as gm
    from casino.dal import bet as dal_bet, game as dal_game, table as dal_table

    svc.domain = Domain("casino")
    svc._sub = svc.domain.subscribe()
    from casino.services.events import register_kinds
    register_kinds(svc.domain)
    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(dal_game, "get_game_hands", return_value=hands + [dealer]), \
         patch.object(dal_game, "get_dealer_hand", return_value=dealer), \
         patch.object(dal_game, "update_game_status"), patch.object(dal_game, "update_game_attrs"), \
         patch.object(dal_game, "get_dealer_hole_card", return_value=None), \
         patch.object(dal_game, "reveal_dealer_hole_card", return_value=None), \
         patch.object(dal_table, "get_table", return_value={"attrs": {}}), \
         patch.object(dal_bet, "get_bet_for_hand", side_effect=lambda a, hid, pool=None: bets.get(hid)), \
         patch.object(dal_bet, "get_insurance", return_value=0), patch.object(dal_bet, "settle_bet"), patch.object(dal_game, "merge_hand_result"), \
         patch.object(gm.dal_player, "increment_stat"), \
         patch.object(svc, "_run_dealer_turn", return_value=["10H", "7D"]):
        svc.settle_game("blackjack-x")
    got = [(e.kind, e.payload["hand_id"], e.payload["result"]) for e in svc.domain.read(svc._sub)]
    assert got == [("hand_settled", 10, "win"), ("hand_settled", 11, "loss")]
