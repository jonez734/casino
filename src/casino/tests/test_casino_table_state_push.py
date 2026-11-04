"""The server pushes casino_table_state to the player's own session on join and leave.

The push carries the seat state the client needs to build its menu and route table verbs:
``moniker`` (the table, or None), ``game_type`` (the table's type, or None), and ``seated``. It is
sent only to the session whose seat changed, never to other sessions. Tests use a fake websocket,
so no database is needed.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from casino.api import handler as h
from casino.api.messages import send_table_state


pytestmark = pytest.mark.unit


class FakeSocket:
    def __init__(self, ident=1):
        self.id = ident
        self.sent = []

    async def send(self, text):
        self.sent.append(json.loads(text))


def _handler():
    obj = h.TableServiceHandler.__new__(h.TableServiceHandler)
    obj.sessions = None
    obj.channel_state = None
    obj.args = SimpleNamespace()
    return obj


def test_state_message_for_a_seated_player():
    msg = h.table_state_message(moniker="blackjack-a", game_type="blackjack", seated=True)
    assert msg == {"type": "casino_table_state", "moniker": "blackjack-a",
                   "game_type": "blackjack", "seated": True}


def test_state_message_when_not_seated_has_no_table():
    msg = h.table_state_message(moniker=None, game_type=None, seated=False)
    assert msg == {"type": "casino_table_state", "moniker": None, "game_type": None, "seated": False}


def test_push_sends_to_the_given_session_only():
    obj = _handler()
    mine, other = FakeSocket(1), FakeSocket(2)
    asyncio.run(send_table_state(mine, moniker="poker-a", game_type="poker", seated=True))
    assert mine.sent == [{"type": "casino_table_state", "moniker": "poker-a",
                          "game_type": "poker", "seated": True}]
    assert other.sent == []


def test_push_failure_is_logged_not_raised():
    class Broken:
        id = 9

        async def send(self, text):
            raise RuntimeError("socket closed")

    obj = _handler()
    # A dead socket must not fail the join or leave that triggered the push.
    asyncio.run(send_table_state(Broken(), moniker=None, game_type=None, seated=False))


class _StubTables:
    def __init__(self, join_ok=True):
        self.join_ok = join_ok

    def join_table(self, **kw):
        return {"success": True, "moniker": kw["moniker"], "game_type": "poker", "message": "joined"}

    def leave_table(self, table_moniker, moniker):
        return {"success": True, "message": "left"}


def _state(moniker="bob"):
    return SimpleNamespace(moniker=moniker, is_sysop=False, session_id=1)


def _full_handler(monkeypatch, tables):
    from casino.dal import table as dal_table
    from casino.services import table_channels as _tc

    # The join handler looks the table up first (for the slots rule). A poker table takes the
    # ordinary path, so only the lookup needs a stand-in; no database is touched.
    monkeypatch.setattr(dal_table, "get_table", lambda *a, **k: {"moniker": "poker-a", "type": "poker"})
    monkeypatch.setattr(_tc, "sync_announcers", lambda *a, **k: None)
    monkeypatch.setattr(_tc, "subscribe_seat", lambda *a, **k: None)
    monkeypatch.setattr(_tc, "unsubscribe_table", lambda *a, **k: None)
    obj = _handler()
    obj._pool = None
    obj.table_service = tables
    obj._check_access = lambda websocket, op, message: (_state(), None)
    obj._set_seated = lambda websocket, table: None
    obj._get_seated = lambda websocket: "poker-a"
    obj._legacy_session_id = lambda websocket: 1
    return obj


def test_join_pushes_the_seated_state_to_the_joining_session(monkeypatch):
    obj = _full_handler(monkeypatch, _StubTables())
    sock = FakeSocket(1)
    reply = asyncio.run(obj._handle_join_table(sock, {"moniker": "poker-a"}))
    assert reply["type"] == "joined_table"
    assert sock.sent == [{"type": "casino_table_state", "moniker": "poker-a",
                          "game_type": "poker", "seated": True}]


def test_leave_pushes_the_unseated_state_to_the_leaving_session(monkeypatch):
    obj = _full_handler(monkeypatch, _StubTables())
    sock = FakeSocket(1)
    reply = asyncio.run(obj._handle_leave_table(sock, {"moniker": "poker-a"}))
    assert reply["type"] == "left_table"
    assert sock.sent == [{"type": "casino_table_state", "moniker": None,
                          "game_type": None, "seated": False}]
