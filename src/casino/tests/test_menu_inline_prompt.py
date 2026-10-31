#!/usr/bin/env python3
# casino/tests/test_menu_inline_prompt.py
# Pins the inline-prompt rendering contract documented at
# handbook/SPEC.md §6.1 ("Menu rendering contract (WS-client inline prompts)").
#
# Two ``io.inputchoice(...)`` call sites join multiple ``[X]label``
# fragments into a single prompt string. Pre-fix they used ``""`` as
# the join separator, so the visible option list rendered as one
# horizontal wall of ``[T]ables,[C]reate,[U]pdate,...`` text and
# was hard to scan. The contract is: exactly one ``{f6}`` between
# adjacent option entries (so ``len(visible) - 1`` total) for the
# WS-client main menu, and exactly one ``{f6}`` between every option
# entry for the bank submenu prompt.
#
# These tests stub out ``bbsengine6.io.inputchoice`` so we can capture
# the prompt string the caller hands in and assert the separator
# count without driving a real terminal.

import argparse
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestClientMenuInlinePrompt(unittest.TestCase):
    """The main menu is read with ``read_menu``. Its prompt carries the player's
    status line and the ``casino_client:`` prompt. The commands are not listed
    inline any more: F1 lists them and tab completes them, so the prompt stays
    short however many commands the menu has.
    """

    def _make_client(self, **overrides):
        """Build a duck-typed CasinoClient stub without importing the real class."""
        defaults = dict(
            moniker="alice",
            balance=100,
            current_table_moniker=None,
            current_table_game_type=None,
            connected=True,
            authenticated=True,
            is_sysop=False,
            owns_tables=False,
            args=None,
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def _prompt(self, client):
        from casino.client import menu as menu_mod

        captured = {}

        def fake_read(prompt, spec, **kw):
            captured["prompt"] = prompt
            captured["spec"] = spec
            return None

        with patch.object(menu_mod, "read_menu", side_effect=fake_read):
            menu_mod.menu(client)
        return captured["prompt"]

    def test_main_menu_prompt_shows_the_status_line(self):
        prompt = self._prompt(self._make_client())
        self.assertIn("alice", prompt)
        self.assertIn("Balance: 100", prompt)
        self.assertIn("casino_client:", prompt)

    def test_main_menu_prompt_shows_the_table_when_seated(self):
        prompt = self._prompt(self._make_client(current_table_moniker="t1",
                                                current_table_game_type="blackjack"))
        self.assertIn("Table: t1", prompt)

    def test_main_menu_prompt_has_no_inline_option_list(self):
        """The old prompt listed every option with [X]; the new one does not."""
        prompt = self._prompt(self._make_client())
        self.assertNotIn("[T]", prompt)
        self.assertNotIn("[Q]", prompt)

    def test_main_menu_prompt_offers_the_word_keys_to_read_menu(self):
        from casino.client import menu as menu_mod

        captured = {}

        def fake_read(prompt, spec, **kw):
            captured["spec"] = spec
            return None

        with patch.object(menu_mod, "read_menu", side_effect=fake_read):
            menu_mod.menu(self._make_client())
        keys = {opt.letter for opt in captured["spec"]}
        self.assertIn("table", keys)
        self.assertIn("quit", keys)
        self.assertNotIn("T", keys, "keys are words, not letters")



class TestBankSubmenuInlinePrompt(unittest.TestCase):
    """Pins that ``CasinoClient.cmd_bank_menu`` produces a prompt
    string with exactly one ``{f6}`` between every adjacent option.
    Drives the loop body directly (skipping the asyncio sleep /
    send plumbing) by patching the methods the loop calls.
    """

    def _make_client(self):
        """Build a CasinoClient instance without running its
        ``__init__`` (which would try to open an event loop).
        """
        from casino.client.casino_client import CasinoClient

        args = argparse.Namespace(bed_host="localhost", bed_port=8765, bed_path="/")
        client = CasinoClient.__new__(CasinoClient)
        client.args = args
        client.moniker = "alice"
        client.balance = 100
        client.current_table_moniker = None
        client.current_table_game_type = None
        client._loop = None
        return client

    def test_bank_submenu_prompt_has_six_f6_separators(self):
        """The bank submenu has 7 options ([B]alance / [A]dd /
        [W]ithdraw / [T]ransfer / [P]ending / [H]istory / [L]ist
        all / [Q]uit). 8 options -> 7 seams, so 7 ``{f6}`` markers
        in the prompt.
        """
        client = self._make_client()

        with patch("bbsengine6.io.inputchoice", return_value="q") as mock_ic:
            client.cmd_bank_menu()

        self.assertEqual(mock_ic.call_count, 1)
        prompt = mock_ic.call_args[0][0]
        # 8 options joined by {f6} -> 7 separators
        self.assertEqual(
            prompt.count("{f6}"),
            7,
            f"expected 7 {{f6}} separators (8 options minus one), "
            f"got {prompt.count('{f6}')} in: {prompt!r}",
        )

    def test_bank_submenu_prompt_quit_terminates_loop(self):
        """The loop exits when ``[Q]uit`` is selected; no second
        ``inputchoice`` call.
        """
        client = self._make_client()

        with patch("bbsengine6.io.inputchoice", return_value="q") as mock_ic:
            client.cmd_bank_menu()

        self.assertEqual(mock_ic.call_count, 1)


if __name__ == "__main__":
    unittest.main()
