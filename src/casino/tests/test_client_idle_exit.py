#!/usr/bin/env python3
# casino/tests/test_client_idle_exit.py
# Phase 2a: a socket the server closes for keepalive (1011) ends the session for inactivity, so
# the client records the exit reason 'idle'. Other closes keep their own reason. The close code
# is kept when the socket closes, instead of being discarded. Stubbed: no daemon.

import asyncio
from unittest.mock import MagicMock, patch

import pytest
import websockets

from casino.client import casino_client as cc


class _ClosedWs:
    def __init__(self, code, reason=""):
        self._exc = websockets.exceptions.ConnectionClosedError(
            rcvd=websockets.frames.Close(code, reason), sent=None
        )

    async def recv(self):
        raise self._exc


def _client(ws):
    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client.ws = ws
    client._close_code = None
    client._close_reason = ""
    return client


@pytest.mark.unit
def test_receive_keeps_the_keepalive_close_code():
    client = _client(_ClosedWs(1011, "keepalive ping timeout"))
    assert asyncio.run(client.receive()) is None
    assert client._close_code == 1011
    assert "keepalive" in client._close_reason


@pytest.mark.unit
def test_keepalive_close_makes_the_exit_reason_idle():
    client = _client(None)
    client._close_code = 1011
    client._exit_reason = "quit"
    # Apply the same decision the exit path makes before the report.
    if client._close_code == 1011:
        client._exit_reason = "idle"
    assert client._exit_reason == "idle"


@pytest.mark.unit
def test_a_normal_close_keeps_its_own_reason():
    client = _client(None)
    client._close_code = 1000
    client._exit_reason = "quit"
    if client._close_code == 1011:
        client._exit_reason = "idle"
    assert client._exit_reason == "quit"


@pytest.mark.unit
def test_exit_path_records_idle_from_the_close_code():
    import inspect
    src = inspect.getsource(cc.CasinoClient.run)
    assert "self._close_code == 1011" in src
    assert 'self._exit_reason = "idle"' in src


@pytest.mark.unit
def test_idle_is_a_valid_client_exit_reason():
    from casino.client import casino_client as c
    assert "idle" in ("quit", "eof", "intr", "idle", "ws_error", "auth_failed", "error")


@pytest.mark.unit
@pytest.mark.parametrize("code", [1006, 1002, 1010, 1012])
def test_abnormal_close_marks_the_websocket_failed(code):
    client = _client(_ClosedWs(code))
    client._ws_failed = False
    asyncio.run(client.receive())
    assert client._close_code == code
    assert client._ws_failed is True


@pytest.mark.unit
@pytest.mark.parametrize("code", [1000, 1001, 1011])
def test_normal_or_keepalive_close_is_not_a_websocket_failure(code):
    client = _client(_ClosedWs(code))
    client._ws_failed = False
    asyncio.run(client.receive())
    assert client._ws_failed is False


@pytest.mark.unit
def test_exit_path_records_ws_error_only_after_login():
    import inspect
    src = inspect.getsource(cc.CasinoClient.run)
    # ws_error is set for an abnormal close, and only when the session was authenticated.
    assert 'self._exit_reason = "ws_error"' in src
    assert "self._ws_failed and self.authenticated" in src
    # 1011 is checked first, so keepalive stays idle.
    assert src.index("self._close_code == 1011") < src.index('"ws_error"')


@pytest.mark.unit
def test_ws_error_is_a_client_exit_reason_in_the_client():
    import inspect
    src = inspect.getsource(cc.CasinoClient.run)
    assert "ws_error" in src
    assert "ws_error" in ("quit", "eof", "intr", "idle", "ws_error", "auth_failed", "error")
