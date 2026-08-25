#!/usr/bin/env python3
"""End-to-end create-member + casino-auth integration tests.

Pins the round-trip the casino BBS stack relies on:

(a) Create a new member and set a simple plaintext password.
    Two paths are covered:
      1. ``bbsengine6.member.setpassword`` -- the public API the
         console uses (``test_console_member_add_edit.py`` already
         exercises it). ``setpassword`` issues
         ``UPDATE engine.__member SET password = crypt($1, gen_salt('bf'))``.
      2. Raw ``INSERT ... crypt('pw', gen_salt('bf'))`` -- the path
         ``test_blackjack_flow.py`` and friends use directly.
    Each path then round-trips the plaintext through
    ``bbsengine6.member.checkpassword`` to prove the crypt(plain, salt)
    match works.

(b) Drive the casino moniker + password prompt
    (``casino.auth.auth_prompt``) end-to-end against an in-process bed
    server whose ``PasswordCredentialProvider`` calls
    ``bbsengine6.member.checkpassword`` for real. The same
    (moniker, password) created in (a) succeeds: server replies with
    ``auth_result.success=True`` and a freshly-minted bearer token.

The two halves share an args namespace / connection pool and a unique
test moniker so reruns against a dirty DB self-heal (every INSERT uses
``ON CONFLICT (moniker) DO UPDATE``).

These tests require:
  - a reachable PostgreSQL DB named ``zoid6`` (or whatever
    ``BBSENGINE6_DBNAME`` / ``--databasename`` says) with the
    ``engine`` schema initialised;
  - the ``websockets`` package (already a casino dependency).

When the DB is unreachable the (a) and (b.2) tests skip with a
``skipTest``; (b.1) runs regardless because it mocks the I/O.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import secrets
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------
# Helpers shared across all three test classes.


def _build_args() -> argparse.Namespace:
    """Build a fully-populated args namespace.

    ``casino.lib.buildargs`` calls ``bbsengine6.database.buildargs``
    which sets ``databaseschema="engine"`` by default -- the bbsengine6
    ``_qualified`` helper reads this to expand ``$engine.member``.
    """
    from casino import lib as casino_lib
    from casino.tests import _dbname

    parser = casino_lib.buildargs()
    return parser.parse_args(_dbname.dbname_args())


def _member_table_reachable(args) -> bool:
    """True iff ``engine.__member`` (or the schema-named equivalent) is queryable."""
    try:
        from bbsengine6 import database

        schema = getattr(args, "databaseschema", "engine") or "engine"
        pool = database.getpool(args)
        try:
            with database.connect(args, pool=pool) as conn, database.cursor(conn) as cur:
                cur.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name = '__member' LIMIT 1",
                    (schema,),
                )
                return cur.fetchone() is not None
        finally:
            pool.close()
    except Exception:
        return False


def _make_unique_moniker(label: str) -> str:
    """Short unique test moniker so reruns against a dirty DB don't collide."""
    return f"{label}_{secrets.token_hex(3)}"


# ---------------------------------------------------------------------
# (a) Create a new member and set a simple password.
#
# Both paths land in the same table; the difference is whether we go
# through the bbsengine6 public API or hand-roll the crypt() call.


class TestCreateMemberAndSetPassword(unittest.IsolatedAsyncioTestCase):
    """Step (a): create a new member, set a password, round-trip through checkpassword."""

    async def asyncSetUp(self):
        from bbsengine6 import database
        from bbsengine6 import member as libmember

        self.args = _build_args()
        self.libmember = libmember

        if not _member_table_reachable(self.args):
            self.skipTest("engine.__member not reachable on this DB")

        self.pool = database.getpool(self.args)
        self.moniker = _make_unique_moniker("alice_test")
        self.password = "pw"

    async def asyncTearDown(self):
        from bbsengine6 import database

        if not hasattr(self, "moniker"):
            return
        try:
            with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
                cur.execute(
                    "DELETE FROM engine.map_member_flag WHERE moniker = %s",
                    (self.moniker,),
                )
                cur.execute(
                    "DELETE FROM engine.__member WHERE moniker = %s",
                    (self.moniker,),
                )
        except Exception:
            pass
        with contextlib.suppress(Exception):
            self.pool.close()

    async def test_a1_create_via_member_setpassword(self):
        """Path A: insert member with NULL password, then call
        ``bbsengine6.member.setpassword``. ``checkpassword`` round-trips True.
        """
        from bbsengine6 import database

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "INSERT INTO engine.__member "
                "(moniker, loginid, email, credits, attrs) "
                "VALUES (%s, %s, %s, %s, %s::jsonb) "
                "ON CONFLICT (moniker) DO UPDATE SET "
                "loginid = EXCLUDED.loginid, "
                "email = EXCLUDED.email, "
                "credits = EXCLUDED.credits, "
                "attrs = EXCLUDED.attrs",
                (
                    self.moniker,
                    self.moniker,
                    f"{self.moniker}@test.local",
                    1000,
                    "{}",
                ),
            )

        result = self.libmember.setpassword(
            self.args, self.password, self.moniker, pool=self.pool
        )
        self.assertIs(
            result,
            True,
            f"setpassword returned {result!r}; expected True",
        )

        self.assertIs(
            self.libmember.has_password(
                self.args, self.moniker, pool=self.pool
            ),
            True,
            "has_password should report True after setpassword",
        )
        self.assertIs(
            self.libmember.checkpassword(
                self.args, self.password, membermoniker=self.moniker,
                pool=self.pool,
            ),
            True,
            "checkpassword should round-trip the plaintext we just set",
        )

    async def test_a2_create_via_raw_crypt_sql(self):
        """Path B: insert with ``password = crypt('pw', gen_salt('bf'))``
        inline. Same two assertions as A: checkpassword / has_password True.
        """
        from bbsengine6 import database

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "INSERT INTO engine.__member "
                "(moniker, loginid, password, email, credits, attrs) "
                "VALUES (%s, %s, crypt(%s, gen_salt('bf')), %s, %s, %s::jsonb) "
                "ON CONFLICT (moniker) DO UPDATE SET "
                "password = crypt(%s, gen_salt('bf'))",
                (
                    self.moniker,
                    self.moniker,
                    self.password,
                    f"{self.moniker}@test.local",
                    1000,
                    "{}",
                    self.password,
                ),
            )

        self.assertIs(
            self.libmember.has_password(
                self.args, self.moniker, pool=self.pool
            ),
            True,
            "has_password should report True after raw crypt insert",
        )
        self.assertIs(
            self.libmember.checkpassword(
                self.args, self.password, membermoniker=self.moniker,
                pool=self.pool,
            ),
            True,
            "checkpassword should round-trip the plaintext inserted via raw SQL",
        )


# ---------------------------------------------------------------------
# (b.1) casino.auth.auth_prompt sends the right wire message.
#
# Mocked. Pins the wire shape ``casino.auth.auth_prompt`` emits
# independent of the server: if a regression drops the ``type`` key
# or swallows the password field, this catches it without spinning up
# the server.


class TestCasinoAuthPromptSendsCredentials(unittest.IsolatedAsyncioTestCase):
    """Step (b.1): the prompt drives ``bed auth``'s prompt + login flow
    and binds the freshly-minted bearer token to casino's WS via
    ``reconnect`` (NOT a fresh ``auth`` envelope -- the prompt UX now
    matches ``bed auth login`` byte-for-byte, and the credential
    round-trip happens through a one-shot ``BedConnection`` so the
    casino WS only ever sees a ``reconnect`` envelope from this
    path)."""

    async def asyncSetUp(self):
        self.moniker = _make_unique_moniker("alice_prompt")
        self.password = "pw"

    async def test_prompt_sends_reconnect_with_token(self):
        from casino import auth

        fake_client = MagicMock()
        fake_client.send = AsyncMock()
        fake_client.moniker = ""
        fake_client.balance = 0
        fake_client.authenticated = False
        fake_client._bearer_token = None

        args = argparse.Namespace()
        args.bed_host = "127.0.0.1"
        args.bed_port = 8765
        args.bed_path = "/"
        args.token_file = None
        args.moniker = None
        args.password = None
        args.debug = False

        def _collect(args):
            from bed.tools import _token as _bed_token
            _bed_token.ensure_token_file_arg(args)
            return (self.moniker, self.password)

        async def _login(moniker, password):
            return {
                "ok": True,
                "moniker": moniker,
                "is_sysop": False,
                "session_id": "sess-1",
                "token": "tok-from-prompt",
                "expires_at": "2099-01-01T00:00:00Z",
                "balance": 100,
            }

        class _FakeConn:
            def __init__(self, args):
                pass

            def force_close(self):
                pass

        class _FakeAuthSvc:
            def __init__(self, conn):
                pass

            login = staticmethod(_login)

        with patch("bed.tools.auth._collect_credentials", side_effect=_collect), \
             patch("bed.tools.auth._persist_token"), \
             patch("bed.client.authservice.BedAuthServiceClient", _FakeAuthSvc), \
             patch("bed.client.connection.BedConnection", _FakeConn):
            result = await auth.auth_prompt(args, fake_client)

        self.assertIs(result, True, "auth_prompt should return True")
        # Casino WS only sees the reconnect envelope; the credential
        # round-trip happens on a one-shot connection.
        fake_client.send.assert_awaited_once_with(
            {"type": "reconnect", "token": "tok-from-prompt"}
        )
        # And the freshly-minted token is stashed on the client so
        # the rest of the session rides it.
        self.assertEqual(fake_client._bearer_token, "tok-from-prompt")
        self.assertTrue(fake_client.authenticated)
        self.assertEqual(fake_client.moniker, self.moniker)
        self.assertEqual(fake_client.balance, 100)


# ---------------------------------------------------------------------
# (b.2) End-to-end through the prompt against an in-process bed server.
#
# Real WebSocket + real ``PasswordCredentialProvider`` (which calls
# ``bbsengine6.member.checkpassword`` for real). Two variants: one
# using the (a.1) ``member.setpassword`` creation path, one using the
# (a.2) raw ``crypt()`` SQL path.


class TestCasinoAuthEndToEnd(unittest.IsolatedAsyncioTestCase):
    """Step (b.2): casino prompt + in-process bed + real password provider."""

    SERVER_START_TIMEOUT = 2.0
    WS_RECV_TIMEOUT = 1.0

    async def _create_member_setpassword_path(self, moniker: str, password: str) -> None:
        """Create member using the (a.1) public API path."""
        from bbsengine6 import database
        from bbsengine6 import member as libmember

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "INSERT INTO engine.__member "
                "(moniker, loginid, email, credits, attrs) "
                "VALUES (%s, %s, %s, %s, %s::jsonb) "
                "ON CONFLICT (moniker) DO UPDATE SET "
                "loginid = EXCLUDED.loginid, "
                "email = EXCLUDED.email, "
                "credits = EXCLUDED.credits, "
                "attrs = EXCLUDED.attrs",
                (
                    moniker,
                    moniker,
                    f"{moniker}@test.local",
                    1000,
                    "{}",
                ),
            )

        self.assertIs(
            libmember.setpassword(self.args, password, moniker, pool=self.pool),
            True,
        )

    async def _create_member_raw_crypt_path(self, moniker: str, password: str) -> None:
        """Create member using the (a.2) raw crypt() SQL path."""
        from bbsengine6 import database

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "INSERT INTO engine.__member "
                "(moniker, loginid, password, email, credits, attrs) "
                "VALUES (%s, %s, crypt(%s, gen_salt('bf')), %s, %s, %s::jsonb) "
                "ON CONFLICT (moniker) DO UPDATE SET "
                "password = crypt(%s, gen_salt('bf'))",
                (
                    moniker,
                    moniker,
                    password,
                    f"{moniker}@test.local",
                    1000,
                    "{}",
                    password,
                ),
            )

    async def _drop_member(self, moniker: str) -> None:
        from bbsengine6 import database

        try:
            with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
                cur.execute(
                    "DELETE FROM engine.map_member_flag WHERE moniker = %s",
                    (moniker,),
                )
                cur.execute(
                    "DELETE FROM engine.__member WHERE moniker = %s",
                    (moniker,),
                )
        except Exception:
            pass

    async def asyncSetUp(self):
        from bbsengine6 import database

        self.args = _build_args()
        if not _member_table_reachable(self.args):
            self.skipTest("engine.__member not reachable on this DB")

        self.pool = database.getpool(self.args)
        self.moniker = _make_unique_moniker("alice_e2e")
        self.password = "pw"

        # Default member created via path (a.1) so b2 tests that omit
        # the per-test recreation don't accidentally see a leftover
        # row from a previous run.
        await self._create_member_setpassword_path(self.moniker, self.password)

        # Spin up an in-process bed server with the REAL
        # ``PasswordCredentialProvider``. The provider calls
        # ``bbsengine6.member.checkpassword`` against this DB so the
        # round-trip we just set up is exactly what the server will
        # verify.
        self._bed_ctx = _BedServerHarness().__enter__()

    async def asyncTearDown(self):
        # Stop server first so the close handshake isn't blocked by
        # a still-open client socket (see bed/tests/_auth_helpers
        # docstring on wait_closed hangs).
        with contextlib.suppress(Exception):
            self._bed_ctx.__exit__(None, None, None)

        if getattr(self, "client_ws", None) is not None:
            with contextlib.suppress(Exception):
                await self.client_ws.close()

        if getattr(self, "moniker", None) is not None:
            await self._drop_member(self.moniker)

        with contextlib.suppress(Exception):
            self.pool.close()

    async def _drive_prompt_and_assert_success(self, moniker: str, password: str):
        """Open a raw WS to the in-process bed, drive ``casino.auth.auth_prompt``
        (which now delegates to ``bed.tools.auth._collect_credentials``
        for the prompt UX), read the reply off the WS, and assert
        that the server's response is a successful ``reconnect_result``
        envelope with a freshly-minted bearer token.

        Note: ``auth_prompt`` opens a one-shot ``BedConnection`` to do
        the credential round-trip -- the casino WS only sees the
        ``reconnect`` envelope (which the server answers with
        ``reconnect_result``). Both hops reach the same in-process
        bed server, so this end-to-end flow still exercises the real
        ``PasswordCredentialProvider`` against the test member.
        """
        from casino import auth
        from casino.client import CasinoClient

        port = self._bed_ctx.port
        self.client_ws = await websockets.connect(f"ws://127.0.0.1:{port}/")

        client = CasinoClient(self.args)
        # Bypass CasinoClient.connect(): hand it the already-open WS so
        # auth_prompt -> client.send -> self.ws.send reaches the server.
        client.ws = self.client_ws
        client.connected = True

        # Build a real BedConnection that talks to the in-process bed
        # via the existing CasinoClient WS. The point of the one-shot
        # connection in production is just to scope a parallel
        # request/response round-trip -- the server sees the same
        # messages either way.
        from bed.client.connection import BedConnection
        one_shot_args = argparse.Namespace()
        one_shot_args.bed_host = "127.0.0.1"
        one_shot_args.bed_port = port
        one_shot_args.bed_path = "/"
        one_shot_args.bed_call_timeout = 5.0
        one_shot_args.bed_probe_timeout = 0.25
        one_shot_conn = BedConnection(one_shot_args)
        # Share the already-open WS so the one-shot connection
        # bypasses its own connect handshake.
        one_shot_conn._ws = self.client_ws

        with patch("bed.tools.auth._collect_credentials", return_value=(moniker, password)), \
             patch("bed.tools.auth._persist_token", return_value=True), \
             patch("bed.client.connection.BedConnection", return_value=one_shot_conn):
            ok = await auth.auth_prompt(self.args, client)

        self.assertIs(ok, True, "auth_prompt should return True")

        reply_raw = await asyncio.wait_for(
            self.client_ws.recv(), timeout=self.WS_RECV_TIMEOUT
        )
        reply = json.loads(reply_raw)
        self.assertEqual(reply.get("type"), "reconnect_result")
        self.assertTrue(
            reply.get("success"),
            f"server replied success=False: {reply!r}",
        )
        self.assertEqual(reply.get("moniker"), moniker)
        self.assertIn("token", reply, f"reconnect_result missing token: {reply!r}")
        # Default-created test member is never a sysop.
        self.assertFalse(reply.get("is_sysop", False))

    async def test_b1_login_through_casino_prompt_setpassword_path(self):
        """End-to-end auth using the member created via bbsengine6.member.setpassword."""
        await self._drive_prompt_and_assert_success(self.moniker, self.password)

    async def test_b2_login_through_casino_prompt_raw_crypt_sql_path(self):
        """End-to-end auth using the member created via raw ``crypt()`` SQL.

        Recreates the member via the (a.2) path so the e2e flow
        exercises every byte the path B path sets, not just the row
        from ``asyncSetUp``.
        """
        await self._drop_member(self.moniker)
        new_moniker = _make_unique_moniker("alice_e2e_b2")
        await self._create_member_raw_crypt_path(new_moniker, self.password)
        # Track the new moniker so tearDown cleans it up.
        self.moniker = new_moniker
        await self._drive_prompt_and_assert_success(self.moniker, self.password)


# ---------------------------------------------------------------------
# (c) Create-member → door-mode ``CasinoPlayer`` auto-materializes the
# casino player row.
#
# This is the round-trip that motivated the lazy-but-auditable
# lifecycle: a freshly-created BBS member should be able to enter the
# door-mode casino menu and have the matching ``casino.__player`` row
# come into existence via ``CasinoPlayer.__init__`` --
# ``ensure_casino_player(...)``, without needing a separate
# ``casino init <moniker>`` step.


class TestCreateMemberThenDoorModeCasinoPlayer(unittest.IsolatedAsyncioTestCase):
    """Step (c): a fresh member's ``CasinoPlayer`` constructor
    materializes the casino row."""

    async def asyncSetUp(self):
        from bbsengine6 import database

        self.args = _build_args()
        if not _member_table_reachable(self.args):
            self.skipTest("engine.__member not reachable on this DB")

        self.pool = database.getpool(self.args)
        self.moniker = _make_unique_moniker("alice_door_casino")
        self.password = "pw"

        # Path (a.1) creates the BBS member only. No casino row yet.
        from bbsengine6 import member as libmember

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "INSERT INTO engine.__member "
                "(moniker, loginid, email, credits, attrs) "
                "VALUES (%s, %s, %s, %s, %s::jsonb) "
                "ON CONFLICT (moniker) DO UPDATE SET "
                "loginid = EXCLUDED.loginid, "
                "email = EXCLUDED.email, "
                "credits = EXCLUDED.credits, "
                "attrs = EXCLUDED.attrs",
                (
                    self.moniker,
                    self.moniker,
                    f"{self.moniker}@test.local",
                    1000,
                    "{}",
                ),
            )
        self.assertIs(
            libmember.setpassword(self.args, self.password, self.moniker, pool=self.pool),
            True,
        )

        # Sanity: no casino row exists for this member yet.
        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "DELETE FROM casino.__player WHERE moniker = %s",
                (self.moniker,),
            )
            cur.execute(
                "SELECT COUNT(*) AS n FROM casino.__player "
                "WHERE moniker = %s",
                (self.moniker,),
            )
            self.assertEqual(cur.fetchone()["n"], 0)

    async def asyncTearDown(self):
        from bbsengine6 import database

        try:
            with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
                cur.execute(
                    "DELETE FROM casino.__player WHERE moniker = %s",
                    (self.moniker,),
                )
                cur.execute(
                    "DELETE FROM engine.__member WHERE moniker = %s",
                    (self.moniker,),
                )
        except Exception:
            pass
        with contextlib.suppress(Exception):
            self.pool.close()

    async def test_c1_door_mode_construction_creates_casino_player_row(self):
        """Constructing ``CasinoPlayer`` for a freshly-created member
        materializes the ``casino.__player`` row. After construction,
        the row is queryable with the expected default attrs and the
        player's ``credits`` / ``lastplayed`` are populated.
        """
        from bbsengine6 import database
        from casino.lib import CasinoPlayer

        player = CasinoPlayer(
            self.args, membermoniker=self.moniker, pool=self.pool
        )

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "SELECT membermoniker, moniker, location, lastplayed, attrs, stats "
                "FROM casino.__player WHERE moniker = %s",
                (self.moniker,),
            )
            row = cur.fetchone()
        self.assertIsNotNone(row, "casino.__player row must exist after CasinoPlayer init")
        self.assertEqual(row["membermoniker"], self.moniker)
        self.assertEqual(row["moniker"], self.moniker)
        self.assertEqual(row["location"], "casino")
        self.assertEqual(row["attrs"], {})
        self.assertEqual(row["stats"], {})

        # The casino player facade populates ``credits`` from
        # engine.__member.credits via the DAL so the bottombar shows
        # the real number (1000 from the seed), not the 1000 placeholder.
        self.assertEqual(player.credits, 1000)
        self.assertEqual(player.moniker, self.moniker)


# ---------------------------------------------------------------------
# Local BedServerContext -- a slim copy of
# bed/src/bed/tests/_auth_helpers.py:BedServerContext scoped to what
# these tests need. Importing the upstream helper would pull in the
# entire bed tests conftest path; keeping a local copy means the file
# is self-contained and works whether or not the upstream helper's
# shim-requirements (sys.path order, package mode) match.


class _BedServerHarness:
    """Sync context manager that runs an in-process bed server in a
    daemon thread with its own asyncio event loop.

    Pattern is identical to
    :class:`bed.tests._auth_helpers.BedServerContext`: the thread keeps
    the loop running so the server can service WebSocket handshakes
    while the test thread's ``asyncio.run`` opens a fresh loop to drive
    the client. On exit every task on the server loop is cancelled
    (``return_exceptions=True``) instead of awaiting
    ``WebSocketServer.stop()`` -- ``stop()`` blocks on
    ``self._server.wait_closed()`` waiting for a client close frame
    that never arrives because the client side already tore down its
    loop. Cancelling tasks is the supported way to abort an asyncio
    server.
    """

    def __init__(self):
        self._loop = None
        self._thread = None
        self.server = None
        self.port = None
        self.auth_service = None
        self.session_registry = None
        self.token_store = None

    def __enter__(self):
        import asyncio
        import socket as _socket
        import threading

        from bbsengine6.net import WebSocketServer
        from bed.api import AuthService, InMemoryTokenStore
        from bed.api.credential_provider import PasswordCredentialProvider
        from bed.api.session import SessionRegistry

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="casino-test-bed",
        )
        self._thread.start()

        secret = secrets.token_bytes(32)

        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]

        registry = SessionRegistry()
        token_store = InMemoryTokenStore()
        # Use the casino args namespace so AuthService's
        # PasswordCredentialProvider -> bbsengine6.member.checkpassword
        # -> _qualified("member", args) sees ``args.databaseschema``
        # (a bare Namespace would trip the UnboundLocalError on the
        # "no databaseschema attr" branch).
        auth_service_args = _build_args()
        auth_service = AuthService(
            args=auth_service_args,
            session_registry=registry,
            token_store=token_store,
            credential_provider=PasswordCredentialProvider(),
            secret=secret,
            instance_id="casino-auth-test",
            ttl_seconds=900,
        )

        server = WebSocketServer(host="127.0.0.1", port=self.port)
        auth_service.register_all(server)

        try:
            future = asyncio.run_coroutine_threadsafe(
                server.start(), self._loop
            )
            future.result(timeout=2.0)
        except BaseException:
            self._safe_shutdown()
            raise

        self.server = server
        self.auth_service = auth_service
        self.session_registry = registry
        self.token_store = token_store
        return self

    def __exit__(self, exc_type, exc, tb):
        self._safe_shutdown()

    def _safe_shutdown(self):
        if self._loop is None:
            return
        try:
            import asyncio

            future = asyncio.run_coroutine_threadsafe(
                self._shutdown_server(), self._loop
            )
            future.result(timeout=2.0)
        except BaseException:
            pass
        with contextlib.suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        try:
            self._loop.close()
        finally:
            self._loop = None
            self._thread = None

    async def _shutdown_server(self):
        import asyncio

        if self.server is None:
            return
        server = self.server
        self.server = None
        ws_server = getattr(server, "_server", None)
        if ws_server is not None:
            try:
                asyncio_server = getattr(ws_server, "server", None)
                if asyncio_server is not None:
                    asyncio_server.close()
            except Exception:
                pass
            try:
                connections = list(ws_server.connections)
            except Exception:
                connections = []
            for conn in connections:
                try:
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


if __name__ == "__main__":
    unittest.main()
