"""The game and bet handlers share one GameService (slice 5).

Each GameService holds the table's shoe and the last settled round, and owns the event domain. If the
game and bet handlers each built their own, a settlement made through one would be invisible to the other
(take_settled_round returns None) and a front end subscribed to one domain would miss the other's events.
"""

from types import SimpleNamespace

import pytest

from casino.api import handler as handler_mod

pytestmark = pytest.mark.unit


def test_the_game_and_bet_handlers_hold_the_same_service_object():
    router = handler_mod.MessageRouter(SimpleNamespace(), config=None)
    game = router.game_service.game_service
    bet = router.bet_service.game_service
    assert game is bet, "the game and bet handlers must share one GameService"


def test_a_settlement_made_through_one_handler_is_taken_through_the_other():
    router = handler_mod.MessageRouter(SimpleNamespace(), config=None)
    game = router.game_service.game_service
    bet = router.bet_service.game_service
    settled = {"outcomes": [{"hand_id": 1, "player": "bob", "result": "win", "bet": 10, "net": 10}]}
    game.__dict__.setdefault("_last_settled", {})["t1"] = settled
    taken = bet.take_settled_round("t1")
    assert taken is not None and taken.has_outcomes


def test_a_subscriber_on_the_shared_service_reads_events_from_both_handlers():
    from unittest.mock import patch

    from casino.services import game as game_mod

    router = handler_mod.MessageRouter(SimpleNamespace(), config=None)
    shared = router.game_service.game_service
    sub = shared.domain.subscribe()
    # The bet handler's service publishes a bet; the game handler's service settles a round.
    bet_service = router.bet_service.game_service
    bet_service._publish_bet("t1", "bob", 10)
    shared._publish_settled("t1", [{"hand_id": 1, "player": "bob", "result": "win", "net": 10}])
    kinds = [e.kind for e in shared.domain.read(sub)]
    assert kinds == ["bet_placed", "hand_settled"]


def test_the_service_exposes_a_reader_for_front_ends():
    router = handler_mod.MessageRouter(SimpleNamespace(), config=None)
    shared = router.game_service.game_service
    sub = shared.subscribe_events()
    shared._publish_expired("t1")
    events = shared.read_events(sub)
    assert [e.kind for e in events] == ["round_expired"]
    assert shared.read_events(sub) == []
