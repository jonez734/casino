#!/usr/bin/env python3
# casino/tests/test_menu_inline_prompt.py
# Pins the inline-prompt rendering contract documented at
# SPEC.md §6.1 ("Menu rendering contract (WS-client inline prompts)").
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
    """Pins that ``casino.client.menu.menu`` produces a prompt string
    with exactly one ``{f6}`` between every adjacent visible option
    (so ``len(visible) - 1`` total).
    """

    def _make_client(self, **overrides):
        """Build a duck-typed CasinoClient stub without importing
        the real class (avoids psycopg / asyncio bring-up).
        """
        defaults = dict(
            moniker="alice",
            balance=100,
            current_table_moniker=None,
            current_table_game_type=None,
            connected=False,
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_main_menu_prompt_has_one_f6_per_option_seam(self):
        """The visible option set is filtered by
        ``visible_options`` (seat / connection gates). For an
        unseated, disconnected client the default 15-entry
        WS-client spec yields 8 visible options. The prompt now
        separates the status prefix (balance) from the option
        list and the option list from the trailing ``casino_client:``
        prompt, so the prompt must contain exactly
        ``len(visible) + 1`` ``{f6}`` markers — 7 between
        options plus the two boundary seams (9 total).
        """
        from casino.client.menu import menu as client_menu

        client = self._make_client()

        with patch("bbsengine6.io.inputchoice", return_value="Q") as mock_ic:
            client_menu(client)

        self.assertEqual(mock_ic.call_count, 1)
        prompt = mock_ic.call_args[0][0]

        # 8 visible options + 2 boundary seams = 9 ``{f6}`` markers
        f6_count = prompt.count("{f6}")
        self.assertEqual(
            f6_count,
            9,
            f"expected 9 {{f6}} separators (8 visible options "
            f"plus balance-tail and prompt-head seams), got "
            f"{f6_count} in: {prompt!r}",
        )

    def test_main_menu_prompt_each_option_on_its_own_line(self):
        """Splitting the prompt on ``{f6}`` gives ``len(visible) + 2``
        chunks: chunk 0 is the bare status prefix (balance), chunks
        1..len(visible) are the per-option entries, and the final
        chunk is the bare trailing ``casino_client:`` prompt. The
        ``{f6}`` markers are exactly the seams between adjacent
        options plus the two boundary seams.
        """
        from casino.client.menu import menu as client_menu
        from casino.client.menu import _visible_options

        client = self._make_client()

        with patch("bbsengine6.io.inputchoice", return_value="Q") as mock_ic:
            client_menu(client)

        prompt = mock_ic.call_args[0][0]
        lines = prompt.split("{f6}")
        # 8 options joined by 7 {f6} + 2 boundary {f6} -> 10 chunks.
        self.assertEqual(len(lines), len(_visible_options(client)) + 2)

        # The first chunk is the status prefix
        # ``[alice] Balance: 100`` alone (no option concatenated).
        self.assertIn("[alice] Balance: 100", lines[0])
        self.assertNotIn("[T]", lines[0])

        # The last chunk is the bare trailing prompt
        # ``casino_client: {var:inputcolor}`` (no option concatenated).
        self.assertEqual(
            lines[-1].rstrip(),
            "{var:promptcolor}casino_client: {var:inputcolor}",
            f"last chunk should be the bare trailing prompt, "
            f"got: {lines[-1]!r}",
        )

    def test_main_menu_prompt_seated_at_blackjack(self):
        """When the player is seated at a blackjack table, the
        seat-gated options become visible (Leave / Bet / Hit /
        Stand). 8 + 4 = 12 visible -> 11 ``{f6}`` between options
        + 2 boundary seams = 13 ``{f6}`` markers.
        """
        from casino.client.menu import menu as client_menu

        client = self._make_client(
            current_table_moniker="bj-1",
            current_table_game_type="blackjack",
        )

        with patch("bbsengine6.io.inputchoice", return_value="Q") as mock_ic:
            client_menu(client)

        prompt = mock_ic.call_args[0][0]
        self.assertEqual(prompt.count("{f6}"), 13)

    def test_main_menu_prompt_seam_count_matches_visible_plus_one(self):
        """General invariant: ``{f6}`` count == ``len(visible) + 1``
        across representative states. This is the contract from
        SPEC.md §6.1: one ``{f6}`` between adjacent options plus
        one ``{f6}`` after the balance and one ``{f6}`` before the
        trailing prompt.
        """
        from casino.client.menu import menu as client_menu
        from casino.client.menu import _visible_options

        cases = [
            # (label, state overrides)
            ("unseated, disconnected", dict()),
            ("connected only",
             dict(connected=True)),
            ("seated at bj",
             dict(current_table_moniker="bj-1",
                  current_table_game_type="blackjack")),
            ("seated at poker",
             dict(current_table_moniker="poker-1",
                  current_table_game_type="poker")),
            ("seated at tictactoe",
             dict(current_table_moniker="tt-1",
                  current_table_game_type="tictactoe")),
        ]
        for label, overrides in cases:
            client = self._make_client(**overrides)
            with patch(
                "bbsengine6.io.inputchoice", return_value="Q"
            ) as mock_ic:
                client_menu(client)
            prompt = mock_ic.call_args[0][0]
            visible = _visible_options(client)
            expected = len(visible) + 1
            actual = prompt.count("{f6}")
            self.assertEqual(
                actual,
                expected,
                f"[{label}] expected {expected} {{f6}} separators "
                f"(len(visible)={len(visible)} + 1 for balance-tail "
                f"and prompt-head seams), got {actual} in: {prompt!r}",
            )

    def test_main_menu_prompt_empty_visible_does_not_crash(self):
        """Defensive: if ``visible_options`` somehow returns an
        empty list (e.g. during a transient state), the prompt must
        still be a valid string with only the two boundary seams
        (balance-tail and prompt-head) and not raise.
        """
        from casino.client.menu import menu as client_menu

        client = self._make_client()

        with patch(
            "bbsengine6.io.inputchoice", return_value="Q"
        ) as mock_ic, patch(
            "casino.client.menu._visible_options", return_value=[]
        ):
            client_menu(client)

        prompt = mock_ic.call_args[0][0]
        self.assertEqual(prompt.count("{f6}"), 2)


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
