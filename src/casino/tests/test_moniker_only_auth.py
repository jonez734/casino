#!/usr/bin/env python3
# casino/tests/test_moniker_only_auth.py
# End-to-end test of the MonikerPromptOnlyAuth pattern documented in auth.py.

import argparse
import asyncio
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


async def moniker_only(args, client) -> bool:
    """MonikerPromptOnlyAuth: no password prompt, sends empty password."""
    from bbsengine6 import io
    moniker = io.inputstring("Moniker: ").strip()
    if not moniker:
        return False
    await client.send({"type": "auth", "moniker": moniker, "password": ""})
    return True


class TestMonikerOnlyAuth(unittest.TestCase):
    """The MonikerPromptOnlyAuth example from auth.py's docstring."""

    def setUp(self):
        from casino import auth
        self._original = auth.auth_prompt
        self._auth_module = auth

    def tearDown(self):
        self._auth_module.auth_prompt = self._original

    def test_subclass_uses_moniker_only(self):
        from casino.client import CasinoClient

        class BotClient(CasinoClient):
            auth_prompt = staticmethod(moniker_only)

        client = BotClient(argparse.Namespace(host="localhost", port=8765))
        seen = []

        async def runner():
            with patch("bbsengine6.io.inputstring", return_value="alice"):
                ok = await client.cmd_auth()
                seen.append(ok)
                return ok

        result = asyncio.run(runner())
        self.assertTrue(result)
        self.assertTrue(seen[-1])

    def test_subclass_aborts_on_empty_moniker(self):
        from casino.client import CasinoClient

        class BotClient(CasinoClient):
            auth_prompt = staticmethod(moniker_only)

        client = BotClient(argparse.Namespace(host="localhost", port=8765))

        async def runner():
            with patch("bbsengine6.io.inputstring", return_value=""):
                return await client.cmd_auth()

        result = asyncio.run(runner())
        self.assertFalse(result)

    def test_module_level_swap_does_not_affect_subclass(self):
        """Subclass override is more specific than module-level swap."""
        from casino.client import CasinoClient

        module_called = []

        async def module_prompt(args, client):
            module_called.append("module")
            return True

        async def class_prompt(args, client):
            module_called.append("class")
            return True

        class BotClient(CasinoClient):
            auth_prompt = staticmethod(class_prompt)

        self._auth_module.auth_prompt = module_prompt
        client = BotClient(argparse.Namespace(host="localhost", port=8765))

        async def runner():
            return await client.cmd_auth()

        asyncio.run(runner())
        self.assertEqual(module_called, ["class"])


if __name__ == "__main__":
    unittest.main()
