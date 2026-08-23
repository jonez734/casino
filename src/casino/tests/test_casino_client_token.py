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


def test_handle_message_captures_token_on_auth_result():
    """``handle_message`` extracts ``token`` from a successful
    ``auth_result`` and stashes it on ``self._bearer_token``.
    Pins the casino-side fix that the prompt-based legacy flow
    was throwing the token away — ``CasinoClient.send`` then
    re-injects it on every op so the server's per-op wire-token
    gate stops rejecting subsequent calls as
    ``not_authenticated``. See
    ``casino/docs/AUTH.md`` §4.
    """
    from unittest.mock import patch

    client = _make_client(_make_args())
    # Stub io.echo so the test does not depend on the echo pipeline.
    with patch("casino.client.casino_client.io.echo"):
        _run(
            client.handle_message(
                {
                    "type": "auth_result",
                    "success": True,
                    "moniker": "alice",
                    "balance": 42,
                    "token": "p.s",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            )
        )
    assert client._bearer_token == "p.s"
    assert client.authenticated is True
    assert client.moniker == "alice"
    assert client.balance == 42


def test_handle_message_omits_token_when_auth_result_has_none():
    """When the server's ``auth_result`` has no ``token`` field
    (legacy standalone / door-mode AuthService envelope), the
    client leaves ``_bearer_token`` at None. ``send`` then
    falls back to session-only payloads so the legacy shape is
    preserved.
    """
    from unittest.mock import patch

    client = _make_client(_make_args())
    assert client._bearer_token is None
    with patch("casino.client.casino_client.io.echo"):
        _run(
            client.handle_message(
                {
                    "type": "auth_result",
                    "success": True,
                    "moniker": "bob",
                    "balance": 0,
                }
            )
        )
    assert client._bearer_token is None
    assert client.authenticated is True


def test_handle_message_strips_whitespace_on_capture():
    """The captured token is stripped of surrounding whitespace
    so a trailing newline from the token file (or a noisy log
    re-emit) does not leak onto the wire.
    """
    from unittest.mock import patch

    client = _make_client(_make_args())
    with patch("casino.client.casino_client.io.echo"):
        _run(
            client.handle_message(
                {
                    "type": "auth_result",
                    "success": True,
                    "moniker": "alice",
                    "balance": 0,
                    "token": "  p.s\n",
                }
            )
        )
    assert client._bearer_token == "p.s"


def test_handle_message_does_not_capture_token_on_failed_auth():
    """A failed ``auth_result`` (``success: false``) leaves
    ``_bearer_token`` untouched. Tokens from a previous
    successful login on the same client are preserved (re-auth
    after disconnect should keep working), but a fresh client
    that fails login does not pick up a junk token from a
    server-supplied error envelope.
    """
    from unittest.mock import patch

    client = _make_client(_make_args())
    assert client._bearer_token is None
    with patch("casino.client.casino_client.io.echo"):
        _run(
            client.handle_message(
                {
                    "type": "auth_result",
                    "success": False,
                    "moniker": "alice",
                    "message": "bad credentials",
                    # Some servers echo a stale token field on error;
                    # we must not capture it.
                    "token": "evil.injected",
                }
            )
        )
    assert client._bearer_token is None
    assert client.authenticated is False


def test_disconnect_awaits_wait_closed():
    """``disconnect`` calls ``ws.close()`` AND ``ws.wait_closed()``.

    Without ``wait_closed()``, the websockets keepalive task is left
    pending after ``close()`` returns. The asyncio loop close path
    then prints "Task was destroyed but it is pending!" at interpreter
    shutdown. ``wait_closed()`` is the websockets-supported wait for
    ``connection_lost`` -- which is what actually cancels the keepalive
    task -- so the loop can be closed cleanly.
    """
    from unittest.mock import patch

    client = _make_client(_make_args())
    ws = MagicMock()
    ws.close = AsyncMock()
    ws.wait_closed = AsyncMock()
    client.ws = ws
    client._receive_task = None

    with patch("casino.client.casino_client.io.echo"):
        _run(client.disconnect())

    ws.close.assert_awaited_once()
    ws.wait_closed.assert_awaited_once()
    assert client.connected is False


def test_disconnect_swallows_wait_closed_errors():
    """If ``wait_closed()`` raises (e.g. the socket is already half-
    closed), the disconnect path still completes so the caller can
    close the loop.
    """
    from unittest.mock import patch

    client = _make_client(_make_args())
    ws = MagicMock()
    ws.close = AsyncMock()
    ws.wait_closed = AsyncMock(side_effect=RuntimeError("already closed"))
    client.ws = ws
    client._receive_task = None

    with patch("casino.client.casino_client.io.echo"):
        _run(client.disconnect())

    ws.close.assert_awaited_once()
    ws.wait_closed.assert_awaited_once()
    assert client.connected is False


# ---------------------------------------------------------------------
# ``casino.auth._close_loop_for`` graceful drain
#
# ``_close_loop_for`` mirrors ``asyncio.run()``'s shutdown sequence
# (cancel pending tasks -> await -> shutdown_asyncgens ->
# shutdown_default_executor -> close). Without the drain,
# websockets' internal ``Connection.keepalive`` task is left pending
# when ``loop.close()`` runs, and Python prints
# ``RuntimeWarning: Task was destroyed but it is pending!`` at
# interpreter shutdown. The tests below pin every branch of the
# helper.


def _make_loop_with_pending_task():
    """Build a real loop with one pending task that hangs forever.

    Returns ``(loop, task)``. The task waits on an ``asyncio.Event``
    that the test never sets, so the only way it ever finishes is via
    the cancel-and-await drain in ``_close_loop_for``.
    """
    loop = asyncio.new_event_loop()
    pending_event = asyncio.Event()

    async def _hang():
        await pending_event.wait()

    task = loop.create_task(_hang())
    # Yield once so the task transitions from ``scheduled`` to
    # actually running (and is observed by ``asyncio.all_tasks``).
    loop.run_until_complete(asyncio.sleep(0))
    return loop, task


def test_close_loop_for_drains_pending_task():
    """A pending task is cancelled and awaited to completion before
    the loop is closed. Without the drain, ``loop.close()`` would
    leave the task pending and Python would warn at GC time.
    """
    from casino.auth import _close_loop_for

    loop, task = _make_loop_with_pending_task()
    assert not task.done()

    _close_loop_for(None, loop=loop)

    assert task.done()
    assert task.cancelled()
    assert loop.is_closed()


def test_close_loop_for_handles_empty_loop():
    """A loop with no pending tasks still closes cleanly."""
    from casino.auth import _close_loop_for

    loop = asyncio.new_event_loop()
    _close_loop_for(None, loop=loop)
    assert loop.is_closed()


def test_close_loop_for_closes_even_if_drain_raises():
    """If a task's cancel handler raises, ``loop.close()`` still runs
    (the ``finally`` block guards it).
    """
    from casino.auth import _close_loop_for

    loop = asyncio.new_event_loop()

    async def _angry():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise RuntimeError("cancel handler angry")

    task = loop.create_task(_angry())
    loop.run_until_complete(asyncio.sleep(0))
    assert not task.done()

    _close_loop_for(None, loop=loop)

    assert loop.is_closed()


def test_close_loop_for_swallows_cancelled_errors():
    """The ``CancelledError`` raised by the drained tasks does not
    propagate out of ``_close_loop_for`` (we use
    ``gather(return_exceptions=True)`` so the drain is itself safe).
    """
    from casino.auth import _close_loop_for

    loop, task = _make_loop_with_pending_task()
    # Should not raise.
    _close_loop_for(None, loop=loop)
    assert task.done()
    assert task.cancelled()


def test_close_loop_for_accepts_client_attribute():
    """When ``loop`` is ``None``, the helper falls back to
    ``client._loop``. This is the production call-site shape used
    everywhere in ``casino.auth`` and ``casino.client``.
    """
    from casino.auth import _close_loop_for

    loop, task = _make_loop_with_pending_task()

    class _StubClient:
        pass

    client = _StubClient()
    client._loop = loop  # type: ignore[attr-defined]

    _close_loop_for(client)

    assert task.done()
    assert task.cancelled()
    assert loop.is_closed()


def test_close_loop_for_no_op_without_loop():
    """When neither ``client._loop`` nor ``loop`` resolves, the helper
    is a silent no-op so call sites don't have to guard against a
    missing loop.
    """
    from casino.auth import _close_loop_for

    class _StubClient:
        pass

    # Should not raise.
    _close_loop_for(_StubClient())
    _close_loop_for(None)
    _close_loop_for(None, loop=None)


def test_close_loop_for_shuts_down_asyncgens():
    """An async generator scheduled before close is finalized through
    ``shutdown_asyncgens`` before the loop is closed.

    The agen must run inside an async function on the loop for the
    ``_asyncgen_firstiter_hook`` to register it (driving ``__anext__``
    via ``run_until_complete`` from outside any coroutine does not
    trigger the hook, so the agen never lands in ``loop._asyncgens``
    and ``shutdown_asyncgens`` would skip it).
    """
    from casino.auth import _close_loop_for

    loop = asyncio.new_event_loop()
    finalized = []
    started = []

    async def _agen():
        started.append("started")
        try:
            yield 1
            yield 2
        finally:
            finalized.append("done")

    async def _drive():
        agen = _agen()
        await agen.__anext__()  # suspended at ``yield 2``
        return agen

    agen = loop.run_until_complete(_drive())
    assert started == ["started"]
    assert finalized == []

    _close_loop_for(None, loop=loop)

    assert finalized == ["done"]
    assert loop.is_closed()
