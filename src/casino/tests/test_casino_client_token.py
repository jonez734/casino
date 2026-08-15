#!/usr/bin/env python3
"""Tests for ``CasinoClient.send`` bearer-token injection.

When ``CasinoClient._bearer_token`` is set (after a token-file connect
or after the server rotates the token on auth), every wire message
must carry ``"token": <token>`` so the server can re-verify it against
its token store on every op. When no token is set, the payload is sent
verbatim so legacy / prompt-based sessions keep the old shape.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, "/home/opencode/data/work/casino/src")


def _make_client(args) -> "CasinoClient":
    from casino.client import CasinoClient

    return CasinoClient(args)


def _make_args() -> argparse.Namespace:
    return argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_send_no_token_injects_nothing():
    """When ``_bearer_token`` is unset, ``send`` does not add a
    ``"token"`` field. Legacy / prompt-based clients keep the
    old payload shape verbatim.
    """
    client = _make_client(_make_args())
    ws = MagicMock()
    ws.send = AsyncMock()
    client.ws = ws
    client._bearer_token = None

    _run(client.send({"type": "auth", "moniker": "alice", "password": "x"}))

    ws.send.assert_awaited_once()
    sent = json.loads(ws.send.await_args.args[0])
    assert sent == {"type": "auth", "moniker": "alice", "password": "x"}
    assert "token" not in sent


def test_send_with_token_injects_token():
    """When ``_bearer_token`` is set, ``send`` copies the message and
    adds ``"token"`` so the original caller's dict is not mutated.
    """
    client = _make_client(_make_args())
    ws = MagicMock()
    ws.send = AsyncMock()
    client.ws = ws
    client._bearer_token = "abc.def"

    msg = {"type": "bet", "amount": 50}
    _run(client.send(msg))

    ws.send.assert_awaited_once()
    sent = json.loads(ws.send.await_args.args[0])
    assert sent == {"type": "bet", "amount": 50, "token": "abc.def"}
    # Original message dict is not mutated.
    assert "token" not in msg


def test_send_strips_whitespace_around_token():
    """The injected token is stripped of surrounding whitespace so a
    trailing newline from the token file does not leak onto the wire.
    """
    client = _make_client(_make_args())
    ws = MagicMock()
    ws.send = AsyncMock()
    client.ws = ws
    client._bearer_token = "  abc.def\n"

    _run(client.send({"type": "list_tables"}))

    sent = json.loads(ws.send.await_args.args[0])
    assert sent["token"] == "abc.def"


def test_send_with_empty_token_does_not_inject():
    """An empty / whitespace-only token is treated as no token so the
    server's wire-token gate stays no-op (consistent with the
    ``secret``-unset behavior).
    """
    client = _make_client(_make_args())
    ws = MagicMock()
    ws.send = AsyncMock()
    client.ws = ws
    client._bearer_token = ""

    _run(client.send({"type": "list_tables"}))

    sent = json.loads(ws.send.await_args.args[0])
    assert "token" not in sent


def test_send_returns_silently_when_ws_unbound():
    """If ``self.ws`` is None, ``send`` is a no-op (matches the
    pre-existing behavior so callers don't need to special-case
    pre-connect sends).
    """
    client = _make_client(_make_args())
    client.ws = None
    client._bearer_token = "abc.def"

    _run(client.send({"type": "bet", "amount": 50}))

    # No exception, no wire activity.


def test_bearer_token_defaults_to_none():
    """A freshly constructed client has ``_bearer_token`` set to None
    so attribute access never raises before the token-file connect.
    """
    client = _make_client(_make_args())
    assert client._bearer_token is None
