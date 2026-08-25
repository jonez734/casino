#!/usr/bin/env python3
# casino/tests/test_auth_prompt.py
# Tests for the D-shape auth_prompt override contract.
#
# The default ``casino.auth.auth_prompt`` delegates the credential
# prompts to ``bed.tools.auth._collect_credentials`` and then logs in
# through a one-shot ``BedAuthServiceClient`` so the prompt UX matches
# ``bed auth login`` byte-for-byte. These tests pin:

# 1. The override contract (module-level swap + CasinoClient subclass
#    override + fall-through resolution).
# 2. The default flow binds the freshly-minted bearer token to the
#    casino client's already-open WebSocket via a ``reconnect``
#    envelope (NOT a fresh ``auth`` envelope), and stashes the token
#    + moniker + balance on the client for the rest of the session.

import argparse
import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")


def _make_fake_client() -> MagicMock:
    """Return a MagicMock that quacks like a CasinoClient for prompt testing."""
    c = MagicMock()
    c.send = AsyncMock()
    c.moniker = ""
    c.balance = 0
    c.authenticated = False
    c._bearer_token = None
    return c


class TestAuthPromptDefault(unittest.TestCase):
    """The default auth_prompt delegates to ``bed auth`` and binds the
    resulting bearer token via ``reconnect`` on the casino WS."""

    def test_default_prompt_delegates_to_bed_and_sends_reconnect(self):
        """The prompt drives ``_collect_credentials`` (so the UX
        matches ``bed auth login``), opens a one-shot BedConnection,
        logs in, persists the token to disk, and binds the fresh
        token to the casino WS via a ``reconnect`` envelope.
        """
        from casino import auth

        async def runner():
            fake_client = _make_fake_client()
            args = argparse.Namespace()
            args.bed_host = "127.0.0.1"
            args.bed_port = 8765
            args.bed_path = "/"
            args.token_file = None

            captured = {}

            def fake_collect(args):
                captured["collect_args"] = args
                return ("alice", "s3cret")

            class FakeOneShotConn:
                _instance_count = 0

                def __init__(self, args):
                    FakeOneShotConn._instance_count += 1
                    self.id = FakeOneShotConn._instance_count

                def force_close(self):
                    captured["force_close"] = True

            class FakeAuthSvc:
                def __init__(self, conn):
                    captured["conn_id"] = conn.id
                    self.conn = conn

                async def login(self, moniker, password):
                    captured["login_call"] = (moniker, password)
                    return {
                        "ok": True,
                        "moniker": moniker,
                        "is_sysop": False,
                        "session_id": "sess-1",
                        "token": "freshly.minted",
                        "expires_at": "2099-01-01T00:00:00Z",
                        "balance": 42,
                    }

            captured["persist_called"] = False

            def fake_persist(reply, bed_args):
                captured["persist_called"] = True
                captured["persist_reply"] = reply
                captured["persist_args"] = bed_args
                return True

            with patch("bed.tools.auth._collect_credentials", side_effect=fake_collect), \
                 patch("bed.tools.auth._persist_token", side_effect=fake_persist), \
                 patch("bed.client.authservice.BedAuthServiceClient", FakeAuthSvc), \
                 patch("bed.client.connection.BedConnection", FakeOneShotConn):
                result = await auth.auth_prompt(args, fake_client)
            return result, fake_client, captured

        result, fake_client, captured = asyncio.run(runner())
        self.assertTrue(result)
        # The bed ``_collect_credentials`` helper was invoked with a
        # bed-shaped namespace (i.e. the prompt UX is identical to
        # ``bed auth login``).
        self.assertIn("collect_args", captured)
        self.assertEqual(captured["collect_args"].subcommand, "login")
        self.assertEqual(captured["collect_args"].bed_host, "127.0.0.1")
        # The login round-trip ran against the one-shot connection.
        self.assertEqual(captured["login_call"], ("alice", "s3cret"))
        self.assertEqual(captured["conn_id"], 1)
        # The token was persisted via bed's helper.
        self.assertTrue(captured["persist_called"])
        self.assertEqual(captured["persist_reply"]["token"], "freshly.minted")
        # Casino WS received a ``reconnect`` envelope, NOT a fresh
        # ``auth`` envelope -- the server binds the token to this WS
        # via ``auth reconnect``.
        fake_client.send.assert_awaited_once_with(
            {"type": "reconnect", "token": "freshly.minted"}
        )
        # Client state was populated synchronously so the rest of the
        # ``run()`` loop can read ``client.authenticated`` /
        # ``client.moniker`` / ``client.balance`` / ``client._bearer_token``
        # without waiting for the server reply.
        self.assertTrue(fake_client.authenticated)
        self.assertEqual(fake_client.moniker, "alice")
        self.assertEqual(fake_client.balance, 42)
        self.assertEqual(fake_client._bearer_token, "freshly.minted")
        # The one-shot connection was force-closed so it does not
        # outlive the prompt.
        self.assertTrue(captured["force_close"])

    def test_default_prompt_empty_moniker_aborts(self):
        """When ``_collect_credentials`` raises ``RuntimeError`` (the
        user provided an empty moniker at the prompt), the prompt
        returns False without sending anything on the casino WS.
        """
        from casino import auth

        async def runner():
            fake_client = _make_fake_client()
            args = argparse.Namespace()
            args.bed_host = "127.0.0.1"
            args.bed_port = 8765
            args.bed_path = "/"
            args.token_file = None

            def fake_collect(args):
                raise RuntimeError("moniker is required")

            with patch("bed.tools.auth._collect_credentials", side_effect=fake_collect):
                result = await auth.auth_prompt(args, fake_client)
            return result, fake_client

        result, fake_client = asyncio.run(runner())
        self.assertFalse(result)
        fake_client.send.assert_not_called()
        self.assertFalse(fake_client.authenticated)
        self.assertIsNone(fake_client._bearer_token)

    def test_default_prompt_soft_failure_returns_false(self):
        """A soft-failure reply from the one-shot login (e.g. bad
        credentials) is rendered via bed's ``_render_soft_failure``
        helper and returns False; the casino WS is not used.
        """
        from casino import auth

        async def runner():
            fake_client = _make_fake_client()
            args = argparse.Namespace()
            args.bed_host = "127.0.0.1"
            args.bed_port = 8765
            args.bed_path = "/"
            args.token_file = None

            rendered = []

            def fake_render(reply):
                rendered.append(reply)

            class FakeOneShotConn:
                def __init__(self, args):
                    pass

                def force_close(self):
                    pass

            class FakeAuthSvc:
                def __init__(self, conn):
                    pass

                async def login(self, moniker, password):
                    return {
                        "ok": False,
                        "code": "bad_credentials",
                        "message": "Invalid moniker or password",
                    }

            with patch("bed.tools.auth._collect_credentials", return_value=("alice", "wrong")), \
                 patch("bed.tools.auth._persist_token") as persist, \
                 patch("bed.tools.auth._render_soft_failure", side_effect=fake_render), \
                 patch("bed.client.authservice.BedAuthServiceClient", FakeAuthSvc), \
                 patch("bed.client.connection.BedConnection", FakeOneShotConn):
                result = await auth.auth_prompt(args, fake_client)
            return result, fake_client, rendered, persist

        result, fake_client, rendered, persist = asyncio.run(runner())
        self.assertFalse(result)
        fake_client.send.assert_not_called()
        self.assertFalse(fake_client.authenticated)
        persist.assert_not_called()
        self.assertEqual(rendered[0]["code"], "bad_credentials")

    def test_default_prompt_missing_token_field_aborts(self):
        """If the server returns ``ok=True`` but omits the ``token``
        field (a malformed auth reply), the prompt refuses to bind a
        junk value and returns False instead of letting the rest of
        the session ride on a missing token.
        """
        from casino import auth

        async def runner():
            fake_client = _make_fake_client()
            args = argparse.Namespace()
            args.bed_host = "127.0.0.1"
            args.bed_port = 8765
            args.bed_path = "/"
            args.token_file = None

            class FakeOneShotConn:
                def __init__(self, args):
                    pass

                def force_close(self):
                    pass

            class FakeAuthSvc:
                def __init__(self, conn):
                    pass

                async def login(self, moniker, password):
                    return {
                        "ok": True,
                        "moniker": moniker,
                        "is_sysop": False,
                        "session_id": "sess-1",
                        # token missing
                        "expires_at": "2099-01-01T00:00:00Z",
                        "balance": 0,
                    }

            with patch("bed.tools.auth._collect_credentials", return_value=("alice", "s3cret")), \
                 patch("bed.tools.auth._persist_token") as persist, \
                 patch("bed.client.authservice.BedAuthServiceClient", FakeAuthSvc), \
                 patch("bed.client.connection.BedConnection", FakeOneShotConn):
                result = await auth.auth_prompt(args, fake_client)
            return result, fake_client, persist

        result, fake_client, persist = asyncio.run(runner())
        self.assertFalse(result)
        fake_client.send.assert_not_called()
        persist.assert_not_called()
        self.assertIsNone(fake_client._bearer_token)


class TestAuthPromptOverride(unittest.TestCase):
    """The override contract: auth.auth_prompt and CasinoClient.auth_prompt."""

    def setUp(self):
        # Save and restore the module-level auth_prompt around each test.
        from casino import auth
        self._original = auth.auth_prompt
        self._auth_module = auth

    def tearDown(self):
        self._auth_module.auth_prompt = self._original

    def test_module_level_swap_is_observed_by_default_prompt_path(self):
        """If we reassign auth.auth_prompt, BBS code can call the new function."""
        called = []

        async def my_prompt(args, client):
            called.append((args, client))
            return True

        self._auth_module.auth_prompt = my_prompt

        async def runner():
            fake_client = _make_fake_client()
            return await self._auth_module.auth_prompt(argparse.Namespace(), fake_client)

        result = asyncio.run(runner())
        self.assertTrue(result)
        self.assertEqual(len(called), 1)

    def test_subclass_auth_prompt_overrides_module_default(self):
        """CasinoClient subclass with its own auth_prompt wins over the module default."""
        from casino.client import CasinoClient

        seen_args = []

        async def my_prompt(args, client):
            seen_args.append(args)
            return True

        class BotClient(CasinoClient):
            auth_prompt = staticmethod(my_prompt)

        client = BotClient(argparse.Namespace(bed_host="localhost", bed_port=8765, bed_path="/"))

        async def runner():
            return await client.cmd_auth()

        result = asyncio.run(runner())
        self.assertTrue(result)
        self.assertEqual(len(seen_args), 1)

    def test_subclass_prompt_receives_self_as_client(self):
        """Subclass prompt gets the CasinoClient instance as its client arg."""
        from casino.client import CasinoClient

        seen_client = []

        async def my_prompt(args, client):
            seen_client.append(client)
            return True

        class BotClient(CasinoClient):
            auth_prompt = staticmethod(my_prompt)

        client = BotClient(argparse.Namespace(bed_host="localhost", bed_port=8765, bed_path="/"))

        async def runner():
            return await client.cmd_auth()

        asyncio.run(runner())
        self.assertIs(seen_client[0], client)

    def test_subclass_default_falls_through_to_module_prompt(self):
        """CasinoClient without auth_prompt falls through to auth.auth_prompt."""
        from casino.client import CasinoClient

        called = []

        async def my_prompt(args, client):
            called.append(client)
            return True

        self._auth_module.auth_prompt = my_prompt

        client = CasinoClient(argparse.Namespace(bed_host="localhost", bed_port=8765, bed_path="/"))
        self.assertIsNone(client.auth_prompt)

        async def runner():
            return await client.cmd_auth()

        result = asyncio.run(runner())
        self.assertTrue(result)
        self.assertEqual(len(called), 1)
        self.assertIs(called[0], client)


if __name__ == "__main__":
    unittest.main()
