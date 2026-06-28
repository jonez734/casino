#!/usr/bin/env python3
# casino/tests/test_auth_prompt.py
# Tests for the D-shape auth_prompt override contract.

import argparse
import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


def _make_fake_client() -> MagicMock:
    """Return a MagicMock that quacks like a CasinoClient for prompt testing."""
    c = MagicMock()
    c.send = AsyncMock()
    return c


class TestAuthPromptDefault(unittest.TestCase):
    """The default auth_prompt sends the right BED message and returns True/False."""

    def test_default_prompt_sends_auth_and_returns_true(self):
        from casino import auth

        async def runner():
            fake_client = _make_fake_client()
            args = argparse.Namespace()
            with patch("casino.auth.io.inputstring", return_value="alice"), \
                 patch("casino.auth.member.has_password", return_value=False):
                result = await auth.auth_prompt(args, fake_client)
            return result, fake_client

        result, fake_client = asyncio.run(runner())
        self.assertTrue(result)
        fake_client.send.assert_awaited_once_with(
            {"type": "auth", "moniker": "alice", "password": ""}
        )

    def test_default_prompt_empty_moniker_aborts(self):
        from casino import auth

        async def runner():
            fake_client = _make_fake_client()
            args = argparse.Namespace()
            with patch("casino.auth.io.inputstring", return_value=""):
                result = await auth.auth_prompt(args, fake_client)
            return result, fake_client

        result, fake_client = asyncio.run(runner())
        self.assertFalse(result)
        fake_client.send.assert_not_called()

    def test_default_prompt_with_password(self):
        from casino import auth

        async def runner():
            fake_client = _make_fake_client()
            args = argparse.Namespace()
            with patch("casino.auth.io.inputstring", return_value="alice"), \
                 patch("casino.auth.member.has_password", return_value=True), \
                 patch("casino.auth.util.inputpassword", return_value="s3cret"):
                result = await auth.auth_prompt(args, fake_client)
            return result, fake_client

        result, fake_client = asyncio.run(runner())
        self.assertTrue(result)
        fake_client.send.assert_awaited_once_with(
            {"type": "auth", "moniker": "alice", "password": "s3cret"}
        )


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

        client = BotClient(argparse.Namespace(host="localhost", port=8765))

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

        client = BotClient(argparse.Namespace(host="localhost", port=8765))

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

        client = CasinoClient(argparse.Namespace(host="localhost", port=8765))
        self.assertIsNone(client.auth_prompt)

        async def runner():
            return await client.cmd_auth()

        result = asyncio.run(runner())
        self.assertTrue(result)
        self.assertEqual(len(called), 1)
        self.assertIs(called[0], client)


if __name__ == "__main__":
    unittest.main()
