"""A game action (hit, stand, double, split, surrender) with no table on the session takes the seat's table.

The bet handler already falls back to the member's seat in the database. Game actions read only the
session's table, so a player who was seated but whose session had no table got ``not_at_table``, which
has no message, and the client printed "Error: None". This pins the same fallback for game actions.
Tests use stand-ins; no database is touched.
"""

import asyncio
from types import SimpleNamespace

import pytest

from casino.api import handler as h


pytestmark = pytest.mark.unit


class _FakeSocket:
    id = 1


class _RecordingGame:
    def __init__(self):
        self.calls = []

    def hit(self, table, player):
        self.calls.append(("hit", table, player))
        return _Result(True)


class _Result:
    def __init__(self, ok):
        self.ok = ok
        self.message = "Hit"
        self.data = {"cards": ["AS"], "total": 11, "status": "playing"}


def _handler(monkeypatch, seat_table):
    from casino import access as access_mod

    monkeypatch.setattr(access_mod, "_seated_table", lambda args, moniker: seat_table)
    obj = h.GameServiceHandler.__new__(h.GameServiceHandler)
    obj.args = SimpleNamespace()
    obj.game_service = _RecordingGame()
    obj.round_event_log = None
    obj._check_access = lambda websocket, op, message: (
        SimpleNamespace(moniker="jam", table_moniker=None, is_sysop=False), None)
    obj._legacy_session_id = lambda websocket: 1
    obj._drain_round_events = lambda: None
    obj._publish_to_table = lambda *a, **k: None

    async def _no_publish(*a, **k):
        return None

    obj._publish_to_table = _no_publish
    obj._get_observers = lambda table: set()
    obj._get_player_count = lambda table: 1
    obj.game_service.get_game_state = lambda table, player: _State()
    obj.game_service.take_settled_round = lambda table: None
    return obj


class _State:
    def to_dict(self):
        return {"table_moniker": "blackjack-jam", "phase": "playing"}


def test_hit_with_no_session_table_uses_the_seat_table(monkeypatch):
    obj = _handler(monkeypatch, seat_table="blackjack-jam")
    reply = asyncio.run(obj._handle_game_action(_FakeSocket(), "hit", {"type": "hit"}))
    assert obj.game_service.calls == [("hit", "blackjack-jam", "jam")]
    assert reply.get("type") != "error"


def test_hit_with_no_table_anywhere_is_not_at_table(monkeypatch):
    obj = _handler(monkeypatch, seat_table=None)
    reply = asyncio.run(obj._handle_game_action(_FakeSocket(), "hit", {"type": "hit"}))
    assert reply == {"type": "error", "code": "not_at_table"}
    assert obj.game_service.calls == []
