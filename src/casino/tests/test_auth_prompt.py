"""Casino's sign-in: bed's shared authenticate does the prompt, login and token store; casino binds the token to its socket.

These tests pin what casino owns: a good sign-in sends a ``reconnect`` with the token and sets the client's identity; a
refusal sends nothing and returns False; the deprecated ``auth_prompt`` name still works, with a DeprecationWarning.
"""

import argparse
import asyncio
import unittest
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

from casino import auth


def _client():
    client = MagicMock()
    client.send = AsyncMock()
    client.moniker = None
    client.balance = 0
    client.authenticated = False
    client._bearer_token = None
    return client


def _args():
    return argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/", token_file=None)


class TestAuthenticate(unittest.TestCase):
    def test_a_good_sign_in_binds_the_token_with_a_reconnect(self):
        client = _client()
        with patch("bed.tools.authenticate.authenticate", return_value=("alice", "freshly.minted")), \
             patch("bed.tools.authenticate.token_directory", return_value="/tmp/x"):
            ok = asyncio.run(auth.authenticate(_args(), client))
        self.assertTrue(ok)
        self.assertEqual(client.moniker, "alice")
        self.assertEqual(client._bearer_token, "freshly.minted")
        self.assertTrue(client.authenticated)
        client.send.assert_awaited_once_with({"type": "reconnect", "token": "freshly.minted"})

    def test_a_refused_sign_in_sends_nothing_and_returns_false(self):
        client = _client()
        with patch("bed.tools.authenticate.authenticate", return_value=("alice", "")), \
             patch("bed.tools.authenticate.token_directory", return_value="/tmp/x"):
            ok = asyncio.run(auth.authenticate(_args(), client))
        self.assertFalse(ok)
        client.send.assert_not_awaited()
        self.assertFalse(client.authenticated)


class TestDeprecatedPromptName(unittest.TestCase):
    def test_auth_prompt_still_signs_in_and_warns(self):
        client = _client()
        with patch("bed.tools.authenticate.authenticate", return_value=("alice", "tok")), \
             patch("bed.tools.authenticate.token_directory", return_value="/tmp/x"), \
             warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ok = asyncio.run(auth.auth_prompt(_args(), client))
        self.assertTrue(ok)
        self.assertTrue(any(issubclass(w.category, DeprecationWarning) for w in caught))


if __name__ == "__main__":
    unittest.main()
