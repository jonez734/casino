"""A leave always replies ``left_table``, even if the table broadcast after it fails.

The client waits for ``left_table``. The broadcast runs before the reply, so an error in it (a database read, a
send) must not stop the reply the client is waiting for.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from casino.api import handler as h


pytestmark = pytest.mark.unit


class _Socket:
    id = "conn-1"

    async def send(self, text):
        return None


def test_a_failed_broadcast_still_replies_left_table(monkeypatch):
    obj = h.TableServiceHandler.__new__(h.TableServiceHandler)
    obj.args = SimpleNamespace()
    obj.channel_state = None
    obj.table_service = MagicMock()
    obj.table_service.leave_table.return_value = {"success": True, "message": "Left table"}
    obj._check_access = lambda websocket, op, message: (SimpleNamespace(moniker="jam"), None)
    obj._get_seated = lambda websocket: "blackjack-jam"
    obj._set_seated = lambda websocket, moniker: None
    obj._legacy_session_id = lambda websocket: 1

    async def broken_broadcast(server, table_moniker):
        raise RuntimeError("database read failed")

    obj._broadcast_table_state = broken_broadcast
    from casino.services import table_channels as _tc
    monkeypatch.setattr(_tc, "sync_announcers", lambda *a, **k: None)
    monkeypatch.setattr(_tc, "unsubscribe_table", lambda *a, **k: None)
    monkeypatch.setattr(h, "send_table_state", _noop_send)

    reply = asyncio.run(obj._handle_leave_table(_Socket(), {"type": "leave_table", "moniker": "blackjack-jam"},
                                                server=object()))

    assert reply["type"] == "left_table"


async def _noop_send(*a, **k):
    return None
