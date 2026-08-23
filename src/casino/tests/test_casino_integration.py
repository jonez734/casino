#!/usr/bin/env python3
"""End-to-end wire-token integration tests for the casino pipeline.

Exercises the full defense-in-depth path:

  1. Start a bed server with ``AuthService`` + ``InMemoryTokenStore``.
  2. Open a WebSocket, send ``auth`` to mint a bearer token.
  3. Open a second WebSocket (fresh, no WS-bound session) and send a
     casino op carrying the token on the wire.
  4. Assert the server-side pipeline re-verifies the token against
     its store on every op and admits the request.

This is the WS-level complement to ``test_auth_integration.py``
(which mocks ``BedAuthServiceClient``). It uses a small
``BedServerContext`` cousin to spin up an in-process server with
auth wired, then drives the casino pipeline through the same JSON
wire shape the production client sends.

The test is intentionally narrow (one happy path + two denial
paths) so it stays fast and stable; broader matrix coverage lives
in :mod:`bed.tests.test_casino_service` and
:mod:`casino.tests.test_casino_access`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import socket as _socket
import sys
import threading
from typing import Any, Dict, Optional

import pytest


sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")


# ---------------------------------------------------------------------
# Helpers


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _send(ws, payload: Dict[str, Any], *, timeout: float = 0.5) -> Dict[str, Any]:
    await ws.send(json.dumps(payload))
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(raw)


def _stub_provider():
    from bed.api.token_store import MemberInfo

    class _Stub:
        def authenticate(self, args, moniker, password, *, pool=None):
            if moniker == "alice" and password == "pw":
                return MemberInfo(
                    moniker="alice",
                    is_sysop=False,
                    balance=7,
                    loginid="alice_os",
                )
            if moniker == "root" and password == "rootpw":
                return MemberInfo(
                    moniker="root",
                    is_sysop=True,
                    balance=0,
                    loginid="root_os",
                )
            return None

    return _Stub()


class _MiniBedServer:
    """Sync context manager: in-process bed server with auth in a
    daemon thread + its own event loop.

    Lighter cousin of :class:`bed.tests._auth_helpers.BedServerContext`,
    scoped to what the casino wire-token tests need.
    """

    def __init__(self, *, secret: Optional[bytes] = None):
        self.secret = secret if secret is not None else secrets.token_bytes(32)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self.server: Any = None
        self.port: Optional[int] = None
        self.auth_service: Any = None
        self.session_registry: Any = None
        self.token_store: Any = None
        self.instance_id = "casino-integration-test"

    def __enter__(self) -> "_MiniBedServer":
        from bbsengine6.net import WebSocketServer
        from bed.api import AuthService, InMemoryTokenStore
        from bed.api.session import SessionRegistry
        from casino.api.handler import MessageRouter

        token_store = InMemoryTokenStore()
        registry = SessionRegistry()
        args = argparse.Namespace(debug=False, pool=None)
        auth_service = AuthService(
            args=args,
            session_registry=registry,
            token_store=token_store,
            credential_provider=_stub_provider(),
            secret=self.secret,
            instance_id=self.instance_id,
            ttl_seconds=900,
        )

        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server = WebSocketServer(host="127.0.0.1", port=port)
        auth_service.register_all(server)
        # Register the casino MessageRouter so its per-op services
        # (list_tables, create_table, join_table, etc.) are wired up.
        # The router shares the same SessionRegistry + AuthService
        # token store / secret / instance_id so the wire-token gate
        # re-verifies on every op exactly as the production stack does.
        casino_router = MessageRouter(
            args,
            session_registry=registry,
            secret=self.secret,
            token_store=token_store,
            instance_id=self.instance_id,
        )
        casino_router.register_all(server)

        loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=loop.run_forever, daemon=True, name="casino-test-server"
        )
        thread.start()
        try:
            future = asyncio.run_coroutine_threadsafe(server.start(), loop)
            future.result(timeout=2.0)
        except BaseException:
            self._safe_shutdown(loop, thread)
            raise

        self._loop = loop
        self._thread = thread
        self.server = server
        self.port = port
        self.auth_service = auth_service
        self.session_registry = registry
        self.token_store = token_store
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._safe_shutdown(self._loop, self._thread)

    def _safe_shutdown(self, loop, thread) -> None:
        if loop is None:
            return
        try:
            if self.server is not None:
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self._shutdown_server(), loop
                    )
                    future.result(timeout=2.0)
                except BaseException:
                    pass
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
            if thread is not None:
                thread.join(timeout=2.0)
        finally:
            try:
                loop.close()
            finally:
                self._loop = None
                self._thread = None

    async def _shutdown_server(self) -> None:
        if self.server is None:
            return
        server = self.server
        self.server = None
        ws_server = getattr(server, "_server", None)
        if ws_server is not None:
            asyncio_server = getattr(ws_server, "server", None)
            if asyncio_server is not None:
                asyncio_server.close()
            try:
                for conn in list(ws_server.connections):
                    transport = getattr(conn, "transport", None)
                    if transport is not None:
                        transport.close()
            except Exception:
                pass
        await asyncio.sleep(0)
        current = asyncio.current_task()
        pending = [t for t in asyncio.all_tasks() if t is not current]
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        del server


def _login(ctx: _MiniBedServer, moniker: str = "alice", password: str = "pw") -> str:
    """Open a fresh WS, send ``auth``, return the token from the reply.

    This drives the production login path (``AuthService._handle_auth``)
    so the token issued here is exactly the format the wire-token
    gate expects.
    """
    import websockets

    async def _drive():
        async with websockets.connect(f"ws://127.0.0.1:{ctx.port}/") as ws:
            reply = await _send(
                ws,
                {"type": "auth", "moniker": moniker, "password": password},
            )
            return reply

    reply = _run(_drive())
    assert reply.get("type") == "auth_result", reply
    assert reply.get("success") is True, reply
    token = reply.get("token") or ""
    assert token, reply
    return token


# ---------------------------------------------------------------------
# Wire-token round-trip tests


def test_wire_token_admits_casino_list_tables():
    """A fresh token issued by the server's login path lets the
    bearer through the wire-token gate. ``list_tables`` is public so
    the policy always allows it once the token is verified.

    The downstream ``table_service.list_tables`` call requires a DB
    pool that this in-process harness does not provide, so we
    accept either the production ``table_list`` envelope OR a
    ``database_error`` envelope -- the point of this test is that
    the auth gate did NOT reject the request. A token failure
    would come back as ``token_invalid`` / ``token_revoked`` /
    ``token_expired`` / ``instance_mismatch``.
    """
    import websockets

    with _MiniBedServer() as ctx:
        token = _login(ctx)

        async def _drive():
            async with websockets.connect(f"ws://127.0.0.1:{ctx.port}/") as ws:
                reply = await _send(
                    ws,
                    {"type": "list_tables", "token": token},
                )
                return reply

        reply = _run(_drive())
        # Auth gate passed: not a token-rejection envelope.
        code = reply.get("code")
        assert code not in (
            "token_invalid",
            "token_revoked",
            "token_expired",
            "instance_mismatch",
            "not_authenticated",
            "no_handler",
        ), reply
        # Either the production table_list envelope OR a downstream
        # DB error is acceptable -- both prove the auth gate let us through.
        assert reply.get("type") in ("table_list", "error"), reply


def test_wire_token_revoked_after_logout_denies_casino_op():
    """After the token is purged from the InMemoryTokenStore, a
    subsequent casino op carrying the same token is denied with a
    token-revoked envelope. Defense-in-depth: the wire token is
    re-verified on every op, not just at connect time.
    """
    import websockets

    with _MiniBedServer() as ctx:
        token = _login(ctx)
        ctx.token_store.delete(token)

        async def _drive():
            async with websockets.connect(f"ws://127.0.0.1:{ctx.port}/") as ws:
                reply = await _send(
                    ws,
                    {"type": "list_tables", "token": token},
                )
                return reply

        reply = _run(_drive())
        assert reply.get("type") == "error"
        # The pipeline translates InMemoryTokenStore's "missing" into
        # a token-revoked envelope (revoked == purged from store).
        assert reply.get("code") == "token_revoked"


def test_wire_token_garbage_denies_casino_op():
    """A bogus / unsigned token fails the HMAC verification gate
    before the policy is consulted, returning a token-invalid
    envelope.
    """
    import websockets

    with _MiniBedServer() as ctx:
        bogus = "abc.def"  # not a real HMAC-signed payload

        async def _drive():
            async with websockets.connect(f"ws://127.0.0.1:{ctx.port}/") as ws:
                reply = await _send(
                    ws,
                    {"type": "list_tables", "token": bogus},
                )
                return reply

        reply = _run(_drive())
        assert reply.get("type") == "error"
        assert reply.get("code") == "token_invalid"


@pytest.mark.filterwarnings("ignore::ResourceWarning")
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_token_rejection_close_loop_does_not_warn():
    """Regression for the user-reported bug.

    When ``casino`` is run with an expired/revoked token, the
    rejection path in ``casino.auth._connect_with_token`` opens a
    WebSocket (which spawns a websockets ``Connection.keepalive``
    task), receives the rejection reply, calls ``disconnect()``,
    then closes the event loop. Before ``_close_loop_for`` was
    introduced, the loop closed while the websockets keepalive
    task was still in pending state -- ``Task.__del__`` then
    reported ``"Task was destroyed but it is pending!"`` via
    ``loop.call_exception_handler`` when the loop was GC'd.

    With ``_close_loop_for`` in place, the loop's pending tasks
    are cancelled and awaited to completion before ``loop.close()``,
    so the handler never fires.

    This test reproduces the exact scenario by driving
    ``_connect_with_token`` against a real ``_MiniBedServer`` with a
    purged token, hooking ``BaseEventLoop.call_exception_handler``
    so we can observe any "Task was destroyed" reports the asyncio
    runtime emits as the loop is GC'd, and asserting none survived.

    We hook at the handler layer (rather than capturing stderr or
    warnings) because asyncio routes the report through
    ``loop.call_exception_handler`` -> the loop's exception handler
    -> (by default) ``logger.error``; pytest's logging plugin
    intercepts the ``asyncio`` logger and discards its output, so
    stderr capture would not see it under pytest.
    """
    import argparse
    import asyncio
    import gc
    import os
    import tempfile

    from casino.auth import _connect_with_token

    captured: list = []
    original_handler = asyncio.base_events.BaseEventLoop.call_exception_handler

    def _capture(self, context):
        captured.append(context)

    asyncio.base_events.BaseEventLoop.call_exception_handler = _capture

    try:
        with _MiniBedServer() as ctx:
            # Issue a real token, then purge it from the store so a
            # subsequent reconnect comes back as ``token_revoked`` --
            # the exact code path the user hit.
            stale = _login(ctx)
            ctx.token_store.delete(stale)

            # Write the stale token to a file the way the casino CLI
            # finds it via ``$XDG_RUNTIME_DIR/bed.token``.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".token", delete=False
            ) as f:
                f.write(stale + "\n")
                token_path = f.name
            try:
                args = argparse.Namespace(
                    token_file=token_path,
                    bed_host="127.0.0.1",
                    bed_port=ctx.port,
                    bed_path="/",
                )

                # The reconnect reply is ``token_revoked`` ->
                # ``_connect_with_token`` returns ``None`` after
                # running the rejection cleanup path.
                result = _connect_with_token(
                    args, "127.0.0.1", ctx.port
                )
                assert result is None

                # Force GC so any pending task is destroyed while
                # our handler is still installed (the
                # "Task was destroyed" report fires from
                # ``Task.__del__`` when the loop is collected).
                gc.collect()

                leaked = [
                    c for c in captured
                    if "destroyed but it is pending" in c.get("message", "")
                ]
                assert leaked == [], (
                    "loop closed with pending task(s); "
                    f"captured handler contexts: "
                    + repr([c.get("message") for c in leaked])
                )
            finally:
                os.unlink(token_path)
    finally:
        asyncio.base_events.BaseEventLoop.call_exception_handler = original_handler
