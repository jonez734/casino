"""Casino's login goes through bed's shared authenticate. The module function and the client hook keep their old names.

The TUI's prompt prompts and logs in through bed's authenticate, then binds the token to the open socket and sets the
client's moniker and balance. Those last two steps are casino's own. The old names are deprecated aliases.
"""

import argparse
import asyncio
import unittest
import warnings
from unittest.mock import AsyncMock, patch

from casino import auth as casino_auth
from casino.client import CasinoClient


class TestAuthenticateIsTheOneCall(unittest.TestCase):
    def test_the_module_authenticate_exists_and_is_the_prompt(self):
        self.assertTrue(callable(casino_auth.authenticate))

    def test_the_old_module_name_is_a_deprecated_alias(self):
        with patch.object(casino_auth, "authenticate", new=AsyncMock(return_value=True)) as new:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                ok = asyncio.run(casino_auth.auth_prompt(argparse.Namespace(), object()))
        self.assertTrue(ok)
        new.assert_awaited_once()
        self.assertTrue(any(issubclass(w.category, DeprecationWarning) for w in caught))


class TestClientHook(unittest.TestCase):
    def test_the_client_hook_is_named_authenticate(self):
        self.assertTrue(hasattr(CasinoClient, "authenticate"))

    def test_the_old_hook_name_still_resolves(self):
        self.assertTrue(hasattr(CasinoClient, "auth_prompt"))


if __name__ == "__main__":
    unittest.main()
