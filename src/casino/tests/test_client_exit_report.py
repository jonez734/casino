#!/usr/bin/env python3
# casino/tests/test_client_exit_report.py
# The client reports why it ended (client_exit) before it disconnects, stops its receiver first,
# and falls back to its own log when there is no live session. Stubbed: no daemon.

import asyncio
import inspect
from unittest.mock import MagicMock, patch

from casino.client import casino_client as cc


def _client(**kw):
    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client.authenticated = kw.get("authenticated", True)
    client.moniker = kw.get("moniker", "jam")
    client._bearer_token = kw.get("token", "tok-live")
    client.ws = kw.get("ws", MagicMock())
    client._receive_task = None
    client.sent = []

    async def _send(msg):
        client.sent.append(msg)

    client.send = _send
    replies = list(kw.get("replies", [{"type": "client_exit_result", "success": True}]))

    async def _receive():
        return replies.pop(0) if replies else None

    client.receive = _receive
    return client


def test_report_sends_client_exit_with_reason_and_moniker():
    client = _client()
    ok = asyncio.run(client._report_exit("eof"))
    assert ok is True
    assert client.sent == [{"type": "client_exit", "moniker": "jam", "reason": "eof"}]


def test_report_returns_false_when_bed_refuses():
    client = _client(replies=[{"type": "client_exit_result", "success": False, "message": "forbidden"}])
    assert asyncio.run(client._report_exit("quit")) is False


def test_no_live_session_writes_only_the_local_log():
    client = _client(authenticated=False)
    with patch.object(cc.io, "echo") as echo:
        ok = asyncio.run(client._report_exit("auth_failed"))
    assert ok is False
    assert client.sent == []
    assert any("not recorded: no live session" in str(c.args[0]) for c in echo.call_args_list)


def test_no_token_means_no_database_row():
    client = _client(token="")
    with patch.object(cc.io, "echo"):
        assert asyncio.run(client._report_exit("error")) is False
    assert client.sent == []


def test_closed_socket_means_no_database_row():
    client = _client(ws=None)
    with patch.object(cc.io, "echo"):
        assert asyncio.run(client._report_exit("intr")) is False
    assert client.sent == []


def test_stop_receiver_cancels_the_background_task_first():
    client = _client()

    async def _forever():
        await asyncio.sleep(3600)

    async def _run():
        client._receive_task = asyncio.get_running_loop().create_task(_forever())
        await client._stop_receiver()
        return client._receive_task

    assert asyncio.run(_run()) is None


def test_run_reports_the_exit_in_the_finally_before_disconnect():
    src = inspect.getsource(cc.CasinoClient.run)
    tail = src[src.rindex("        finally:"):]
    assert tail.index("_stop_receiver()") < tail.index("_report_exit(")
    assert tail.index("_report_exit(") < tail.index("disconnect())")
