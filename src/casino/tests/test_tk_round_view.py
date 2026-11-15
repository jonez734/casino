"""The Tk round view renders the round's events, in order, from a subscription (slice 6, Tk front end).

The view is a model plus a thin Tk layer. These tests exercise the model: it takes events from a
subscription and produces the lines the window shows. They need no display.
"""

from types import SimpleNamespace

import pytest

from casino.tk import roundview

pytestmark = pytest.mark.unit


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

    def publish(self, kind, scope, moniker, payload):
        from bbsengine6.seam.events import Event

        self.domain.emit(Event(kind, scope, moniker, payload))


def test_the_model_turns_events_into_lines_in_order():
    svc = _Svc()
    view = roundview.RoundViewModel(svc)
    svc.publish("bet_placed", "t1", "bob", {"amount": 10})
    svc.publish("card_dealt", "t1", None, {"card": "10H"})
    svc.publish("hand_settled", "t1", "bob", {"hand_id": 3, "result": "win", "net": 10})
    svc.publish("round_expired", "t1", None, {})
    lines = view.poll()
    assert lines == [
        "bob bet 10",
        "dealt 10H",
        "bob hand 3: win, net +10",
        "round expired",
    ]


def test_poll_returns_only_new_events():
    svc = _Svc()
    view = roundview.RoundViewModel(svc)
    svc.publish("card_dealt", "t1", None, {"card": "2S"})
    assert view.poll() == ["dealt 2S"]
    assert view.poll() == []


def test_a_lagged_marker_is_shown_as_a_line():
    from bbsengine6.seam.kinds import LAGGED_KIND  # noqa: F401  (the kind the seam emits)

    svc = _Svc()
    view = roundview.RoundViewModel(svc)
    from bbsengine6.seam.events import Event

    # The seam emits "lagged" when a subscriber falls behind; the view says so rather than dropping it.
    view._handle(Event("lagged", "", None, {"missed": 4}))
    assert view.lines == ["missed 4 events (fell behind)"]


def test_the_view_schedules_its_poll_on_the_tk_loop():
    # A Tk app drains on its own loop: the view asks the window to call poll() again later.
    svc = _Svc()
    scheduled = []
    window = SimpleNamespace(after=lambda ms, fn: scheduled.append((ms, fn)))
    view = roundview.RoundViewModel(svc)
    roundview.start_polling(window, view, interval_ms=200)
    assert scheduled and scheduled[0][0] == 200


def test_a_real_lag_through_the_seam_reaches_the_window_lines():
    from bbsengine6.seam.domain import Domain
    from casino.services.events import register_kinds

    class _Small(_Svc):
        def __init__(self):
            from bbsengine6.seam.domain import Domain as D
            from casino.services.events import register_kinds as r

            self.domain = D("casino", capacity=3)
            r(self.domain)

    svc = _Small()
    view = roundview.RoundViewModel(svc)
    for i in range(6):
        svc.publish("card_dealt", "t1", None, {"card": f"{i}H"})
    lines = view.poll()
    assert lines[0].startswith("missed ") and "fell behind" in lines[0]
    assert lines[1:] == ["dealt 3H", "dealt 4H", "dealt 5H"]


def test_the_window_builds_when_a_display_is_available():
    import pytest as _pytest

    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
    except tkinter.TclError:
        _pytest.skip("no display for tkinter")
    root.destroy()
    window = roundview.build_window(_Svc())
    assert window.model is not None
    window.destroy()


def test_the_model_shows_only_the_watched_table():
    svc = _Svc()
    view = roundview.RoundViewModel(svc, table="t1")
    svc.publish("card_dealt", "t1", None, {"card": "2S"})
    svc.publish("card_dealt", "t2", None, {"card": "9D"})
    assert view.poll() == ["dealt 2S"]


def test_a_game_state_message_from_the_daemon_becomes_lines():
    # The viewer is a client of the daemon: it turns the game_state messages the daemon already sends
    # into lines. Round results come from round_settled, the same as the TUI shows them.
    model = roundview.WireRoundViewModel()
    model.feed({
        "type": "game_state",
        "table_moniker": "blackjack-x",
        "phase": "dealer",
        "player_hand": ["10H", "7D"],
        "player_total": 17,
        "dealer_hand": ["10S", "9C"],
        "dealer_total": 19,
        "round_settled": {
            "outcomes": [{"player": "bob", "result": "loss", "bet": 10, "net": -10, "text": "lost to dealer 19"}],
            "net": -10,
        },
    })
    assert "Your hand: 10H 7D [17]" in model.lines
    assert "Dealer: 10S 9C [19]" in model.lines
    assert "Result (bob): lost to dealer 19" in model.lines
    assert "Round net: -10" in model.lines


def test_a_non_state_message_is_ignored():
    model = roundview.WireRoundViewModel()
    model.feed({"type": "chat", "text": "hi"})
    assert model.lines == []
