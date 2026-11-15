"""A headless subscriber logs a round's events, in order, from the shared service (slice 6).

The subscriber reads only through subscribe_events / read_events, so it has no wire effect. A round played
through the publishers yields bet_placed, card_dealt, hand_settled and round_expired, in that order.
"""

from types import SimpleNamespace

import pytest

from casino.services import round_event_log as log

pytestmark = pytest.mark.unit


class _Line:
    """One logged line: the format string and the arguments it was given."""

    def __init__(self, msg, args):
        self.msg = msg
        self.args = args


class _Svc:
    def __init__(self):
        from bbsengine6.seam.domain import Domain
        from casino.services.events import register_kinds

        self.domain = Domain("casino")
        register_kinds(self.domain)

    def subscribe_events(self, *, debug=False):
        return self.domain.subscribe(debug=debug)

    def read_events(self, sub):
        return self.domain.read(sub)

    def _publish(self, kind, scope, moniker, payload):
        from bbsengine6.seam.events import Event

        self.domain.emit(Event(kind, scope, moniker, payload))


def test_a_round_is_logged_in_order_from_one_subscriber():
    svc = _Svc()
    seen = []
    sink = SimpleNamespace(info=lambda msg, *a: seen.append(_Line(msg, a)))
    subscriber = log.RoundEventLog(svc, sink)

    svc._publish("bet_placed", "t1", "bob", {"amount": 10})
    svc._publish("card_dealt", "t1", None, {"card": "10H"})
    svc._publish("hand_settled", "t1", "bob", {"hand_id": 3, "result": "win", "net": 10})
    svc._publish("round_expired", "t1", None, {})
    subscriber.drain()

    # The sink receives the format string and its arguments; the kind is the first argument.
    kinds = [m.args[0] for m in seen]
    assert kinds == ["bet_placed", "card_dealt", "hand_settled", "round_expired"]


def test_drain_logs_nothing_when_no_events_are_waiting():
    svc = _Svc()
    seen = []
    subscriber = log.RoundEventLog(svc, SimpleNamespace(info=lambda msg, *a: seen.append(msg)))
    subscriber.drain()
    assert seen == []


def test_the_subscriber_has_no_wire_effect():
    # It only reads the domain: it never sends to a client.
    import inspect

    src = inspect.getsource(log)
    assert "websocket" not in src and ".send(" not in src


def test_the_router_wires_one_round_event_log_on_the_shared_service():
    from casino.api import handler as handler_mod

    router = handler_mod.MessageRouter(SimpleNamespace(), config=None)
    log_ = router.round_event_log
    assert log_._service is router.game_service.game_service
    assert log_._service is router.bet_service.game_service


def test_a_service_handler_without_a_log_still_drains_safely():
    # Regression: the service handlers call drain after an action. A handler built without a subscriber
    # (standing alone) must not raise, or the action's reply is lost.
    from casino.api import handler as handler_mod

    handler = handler_mod.GameServiceHandler.__new__(handler_mod.GameServiceHandler)
    handler.round_event_log = None
    handler._drain_round_events()  # must not raise


def test_the_service_handlers_share_the_routers_log():
    from casino.api import handler as handler_mod

    router = handler_mod.MessageRouter(SimpleNamespace(), config=None)
    assert router.game_service.round_event_log is router.round_event_log
    assert router.bet_service.round_event_log is router.round_event_log
