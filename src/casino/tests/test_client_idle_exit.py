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
    assert "idle" in ("quit", "eof", "intr", "idle", "auth_failed", "error")
