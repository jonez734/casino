"""The round viewer's login is bed's shared authenticate. The viewer keeps only the choice to reuse a stored token.

A stored token that the daemon still accepts is reused, with no prompt. Otherwise the viewer calls bed's authenticate,
which prompts, logs in, and stores the token for this player and terminal.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from casino.tk import viewer_login


class TestEnsureToken(unittest.TestCase):
    def test_a_usable_stored_token_is_reused_without_a_prompt(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(viewer_login, "_authenticate") as auth:
            path = viewer_login.token_name.token_file_path(d, "jam")
            with open(path, "w") as fh:
                fh.write("tok-stored")
            os.chmod(path, 0o600)
            moniker, token = viewer_login.ensure_token(d, "jam", is_usable=lambda t: True)
        auth.assert_not_called()
        self.assertEqual((moniker, token), ("jam", "tok-stored"))

    def test_no_usable_token_calls_the_shared_authenticate(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(viewer_login, "_authenticate", return_value=("jam", "tok-new")) as auth:
            moniker, token = viewer_login.ensure_token(d, "", is_usable=lambda t: True)
        auth.assert_called_once()
        self.assertEqual((moniker, token), ("jam", "tok-new"))

    def test_a_refused_login_returns_no_token(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(viewer_login, "_authenticate", return_value=("jam", "")):
            _, token = viewer_login.ensure_token(d, "", is_usable=lambda t: True)
        self.assertEqual(token, "")


if __name__ == "__main__":
    unittest.main()
