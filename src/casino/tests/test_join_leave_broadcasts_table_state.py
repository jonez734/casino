"""A join or leave broadcasts the table's game_state to everyone watching it.

Before this, a player who sat down at an idle table, or stood up, sent nothing to the table's
channel. A viewer (or any spectator) only learned of the seat change on the next bet or action.
The broadcast carries the seats, including between rounds, so the viewer shows the change at once.
Tests use stand-ins for the database and the channel; no database is touched.
"""

import asyncio
from types import SimpleNamespace

import pytest

from casino.api import handler as h
from casino.api.payloads import GameState
from casino.dal import table as dal_table_mod
from casino.services import game as game_mod
from casino.tests.test_casino_table_state_push import FakeSocket, _StubTables, _full_handler


pytestmark = pytest.mark.unit


class _RecordingServer:
    """Stands in for the bed server: records every table publish."""

    def __init__(self):
        self.published = []


def _capture_publish(monkeypatch, obj):
    """Replace the table publish with a recorder, so the broadcast can be read back."""
    async def fake_publish(self_, server, table_moniker, message, sender_moniker):
        server.published.append((table_moniker, message))

    obj._publish_to_table = fake_publish.__get__(obj)


def _waiting_state(table_moniker, seats):
    """The state the service returns between rounds, with the seats the join has just changed."""
    return {"table_moniker": table_moniker, "phase": "waiting", "hands": [], "seats": seats,
            "player_hand": [], "dealer_hand": [], "insurance_available": False, "insurance_taken": 0}


class _Sink:
    """Stands in for the transport: records each per-session send."""

    def __init__(self):
        self.sent = []

    async def send_to_session(self, session_id, message):
        self.sent.append((session_id, message))


def _join_handler(monkeypatch, watchers, seats_for):
    obj = _full_handler(monkeypatch, _StubTables())
    obj.game_service = SimpleNamespace(
        get_game_state=lambda table, player, deal=True: GameState.from_dict(_waiting_state(table, [])),
        _pool=None,
    )
    obj.args = SimpleNamespace()
    obj.sessions = SimpleNamespace(
        get_table_observers=lambda t: set(watchers),
        sessions_for_moniker=lambda m: seats_for.get(m, []),
    )
    from casino.dal import table as dal_table

    monkeypatch.setattr(dal_table, "seated_monikers", lambda *a, **k: list(seats_for))
    return obj


def test_join_sends_each_seat_its_view_and_watchers_the_public_state(monkeypatch):
    obj = _join_handler(monkeypatch, watchers={"conn-9"}, seats_for={"bob": ["conn-1"]})
    sink = _Sink()
    reply = asyncio.run(obj._handle_join_table(FakeSocket(1), {"moniker": "poker-a"}, server=sink))
    assert reply["type"] == "joined_table"
    sent_ids = [sid for sid, _ in sink.sent]
    assert "conn-9" in sent_ids, "the watcher gets the public state"
    assert "conn-1" in sent_ids, "the seated player gets their own view"


def test_leave_sends_each_seat_its_view_and_watchers_the_public_state(monkeypatch):
    obj = _join_handler(monkeypatch, watchers={"conn-9"}, seats_for={"bob": ["conn-1"]})
    sink = _Sink()
    reply = asyncio.run(obj._handle_leave_table(FakeSocket(1), {"moniker": "poker-a"}, server=sink))
    assert reply["type"] == "left_table"
    assert "conn-9" in [sid for sid, _ in sink.sent]


def test_a_join_with_no_server_publishes_nothing(monkeypatch):
    # Direct callers (tests, tools) pass no server; the join must still succeed without a broadcast.
    obj = _full_handler(monkeypatch, _StubTables())
    published = []

    async def fake_publish(server, table_moniker, message, sender_moniker):
        published.append(table_moniker)

    obj._publish_to_table = fake_publish.__get__(obj)
    reply = asyncio.run(obj._handle_join_table(FakeSocket(1), {"moniker": "poker-a"}))
    assert reply["type"] == "joined_table"
    assert published == []


def test_the_waiting_state_lists_the_seated_players(monkeypatch):
    # Between rounds the state must still name who is seated, or a join at an idle table is invisible.
    from casino.dal import game as dal_game
    from casino.dal import table as dal_table

    service = game_mod.GameService.__new__(game_mod.GameService)
    service.args = SimpleNamespace()
    service._pool = None
    monkeypatch.setattr(dal_table, "get_table", lambda *a, **k: {"moniker": "t", "attrs": {}})
    monkeypatch.setattr(dal_game, "get_current_game", lambda *a, **k: None)
    monkeypatch.setattr(dal_table, "seated_monikers", lambda *a, **k: ["jam"])

    state = service.get_game_state("t", "jam").to_dict()

    assert state["phase"] == "waiting"
    assert [s["player"] for s in state["seats"]] == ["jam"]


def test_a_join_broadcast_never_deals_the_dealer(monkeypatch):
    # A round with hands but no dealer cards yet is dealt by the bet, not by a join's table broadcast.
    # The broadcast reads the state; if it dealt, the shoe would be drawn out of order.
    from casino.dal import game as dal_game

    service = game_mod.GameService.__new__(game_mod.GameService)
    service.args = SimpleNamespace()
    service._pool = None
    drawn = []
    service._draw_card = lambda table: drawn.append(table) or "AS"
    monkeypatch.setattr(dal_table_mod, "get_table", lambda *a, **k: {"moniker": "t", "attrs": {}})
    monkeypatch.setattr(dal_game, "get_current_game", lambda *a, **k: {"id": 7, "status": "playing"})
    monkeypatch.setattr(dal_game, "get_player_hands", lambda *a, **k: [{"id": 1, "cards": ["9S", "8H"], "attrs": {}}])
    monkeypatch.setattr(dal_game, "get_dealer_hand", lambda *a, **k: None)
    monkeypatch.setattr(dal_game, "create_dealer_hand", lambda *a, **k: None)
    monkeypatch.setattr(dal_game, "update_dealer_hand_cards", lambda *a, **k: None)
    monkeypatch.setattr(dal_game, "set_dealer_hole_card", lambda *a, **k: None)
    monkeypatch.setattr(dal_game, "get_game_hands", lambda *a, **k: [])
    monkeypatch.setattr(dal_table_mod, "seated_monikers", lambda *a, **k: [])
    from casino.dal import bet as dal_bet
    monkeypatch.setattr(dal_bet, "get_bet_for_hand", lambda *a, **k: None)

    service.get_game_state("t", "", deal=False)

    assert drawn == [], "a join's broadcast must not draw cards from the shoe"
