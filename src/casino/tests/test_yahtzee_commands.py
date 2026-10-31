#!/usr/bin/env python3
# casino/tests/test_yahtzee_commands.py
# Tests for the yahtzee commands shim and the module.run() dispatch flow
# that connects casino.main's "Y" Yahtzee menu entry to the local game.
#
# Mirrors tests/test_slots_commands.py so future contributors find
# the same Test* classes with the same shape across both games.

import argparse
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")


def _make_args(**overrides) -> argparse.Namespace:
    base = {"debug": False}
    base.update(overrides)
    return argparse.Namespace(**base)


class TestCommandsYahtzeePackage(unittest.TestCase):
    """The commands.yahtzee shim must exist and expose the expected surface."""

    def test_package_importable(self):
        import casino.commands.yahtzee

        self.assertTrue(hasattr(casino.commands.yahtzee, "SUBCOMMANDS"))
        self.assertTrue(hasattr(casino.commands.yahtzee, "main"))
        self.assertTrue(hasattr(casino.commands.yahtzee, "init"))
        self.assertTrue(hasattr(casino.commands.yahtzee, "access"))
        self.assertTrue(hasattr(casino.commands.yahtzee, "buildargs"))

    def test_subcommands_dict_has_play(self):
        from casino.commands.yahtzee import SUBCOMMANDS

        self.assertIn("play", SUBCOMMANDS)
        self.assertTrue(callable(SUBCOMMANDS["play"]))

    def test_lib_exports(self):
        from casino.commands.yahtzee.lib import menu, play

        self.assertTrue(callable(play))
        self.assertTrue(callable(menu))


class TestCommandsYahtzeeResolveSubcommand(unittest.TestCase):
    """Subcommand prefix resolution for the yahtzee commands shim."""

    def test_exact_match(self):
        from casino.commands.yahtzee import _resolve_subcommand

        self.assertEqual(_resolve_subcommand("play"), "play")

    def test_partial_match(self):
        from casino.commands.yahtzee import _resolve_subcommand

        self.assertEqual(_resolve_subcommand("pl"), "play")

    def test_empty_returns_none(self):
        from casino.commands.yahtzee import _resolve_subcommand

        self.assertIsNone(_resolve_subcommand(""))

    def test_no_match_returns_none(self):
        from casino.commands.yahtzee import _resolve_subcommand

        self.assertIsNone(_resolve_subcommand("xyz"))


class TestCommandsYahtzeeMainDispatch(unittest.TestCase):
    """commands.yahtzee.main dispatches subcommands via SUBCOMMANDS."""

    def test_no_subcommand_invokes_menu(self):
        from casino.commands.yahtzee import main

        with patch("casino.commands.yahtzee.lib.menu") as mock_menu:
            result = main(_make_args())
        mock_menu.assert_called_once()
        self.assertTrue(result)

    def test_known_subcommand_invokes_callback(self):
        from casino.commands.yahtzee import SUBCOMMANDS, main

        mock_cb = MagicMock(return_value=True)
        original = SUBCOMMANDS["play"]
        SUBCOMMANDS["play"] = mock_cb
        try:
            result = main(_make_args(), subcommand="play")
        finally:
            SUBCOMMANDS["play"] = original
        mock_cb.assert_called_once()
        self.assertTrue(result)

    def test_ambiguous_or_unknown_subcommand_falls_back_to_menu(self):
        from casino.commands.yahtzee import main

        with patch("casino.commands.yahtzee.lib.menu") as mock_menu:
            result = main(_make_args(), subcommand="nonexistent")
        mock_menu.assert_called_once()
        self.assertTrue(result)


class TestYahtzeePackageMainUsesModuleRun(unittest.TestCase):
    """casino.yahtzee.main() must route through module.run() so callers like
    casino.yahtzee.__main__ get the standard machinery (registration,
    buildargs, signature checks)."""

    def test_init_main_delegates_to_module_run(self):
        import casino.yahtzee

        sentinel = object()
        with patch("bbsengine6.module.run", return_value=sentinel) as mock_run:
            result = casino.yahtzee.main(_make_args(), extra_kw="value")

        self.assertIs(result, sentinel)
        mock_run.assert_called_once()
        args_, kwargs = mock_run.call_args
        self.assertEqual(args_[1], "game")
        self.assertEqual(kwargs.get("package"), "casino.yahtzee")
        self.assertEqual(kwargs.get("extra_kw"), "value")


class TestModuleCheckPasses(unittest.TestCase):
    """bbsengine6.module.check() must accept the new yahtzee modules."""

    def test_commands_yahtzee_passes(self):
        from bbsengine6 import module

        self.assertTrue(
            module.check(_make_args(), "yahtzee", package="casino.commands")
        )

    def test_yahtzee_package_passes(self):
        from bbsengine6 import module

        self.assertTrue(module.check(_make_args(), "casino.yahtzee"))

    def test_yahtzee_game_passes(self):
        from bbsengine6 import module

        self.assertTrue(
            module.check(_make_args(), "game", package="casino.yahtzee")
        )


class TestYahtzeeGameRegistersItself(unittest.TestCase):
    """casino.yahtzee.game.init() must call register_module() so bbsengine6
    recognizes the inner game module."""

    def test_game_init_calls_register_module(self):
        from casino.yahtzee import game

        with patch("casino.yahtzee.game.register_module") as mock_reg:
            result = game.init(_make_args())

        self.assertTrue(result)
        mock_reg.assert_called_once()
        kwargs = mock_reg.call_args.kwargs
        self.assertEqual(kwargs.get("name"), "casino.yahtzee.game")
        self.assertEqual(kwargs.get("module_path"), "casino.yahtzee.game")


class TestYahtzeeGameMainSetsUpDealerAndPlayer(unittest.TestCase):
    """casino.yahtzee.game.main() must build a YahtzeeDealer + YahtzeePlayer
    and delegate to casino.yahtzee.play.main() with those kwargs."""


class TestYahtzeeMenuHelpWiring(unittest.TestCase):
    """commands/yahtzee/lib.py:menu() must wire help= so KEY_HELP redraws the
    option list. The help callback must call util.heading() exactly once
    per display of help (one F1 press -> one heading)."""

    def test_menu_passes_help_to_inputchoice(self):
        from casino.commands.yahtzee import lib

        with patch("bbsengine6.io.inputchoice", return_value="q") as mock_ic:
            lib.menu(_make_args())

        mock_ic.assert_called_once()
        kwargs = mock_ic.call_args.kwargs
        self.assertIn("help", kwargs)
        self.assertTrue(callable(kwargs["help"]))

    def test_help_callback_calls_heading_exactly_once(self):
        """Simulate one F1 press: util.heading() must be called exactly once."""
        from casino.commands.yahtzee import lib

        with patch("bbsengine6.io.inputchoice") as mock_ic, \
             patch("casino.commands.yahtzee.lib.util.heading") as mock_heading:
            lib.menu(_make_args())
            mock_heading.reset_mock()
            mock_ic.call_args.kwargs["help"]()
        self.assertEqual(mock_heading.call_count, 1)

    def test_help_callback_uses_yahtzee_heading(self):
        """The heading title must be 'Yahtzee' so F1 shows the right banner."""
        from casino.commands.yahtzee import lib

        with patch("bbsengine6.io.inputchoice") as mock_ic, \
             patch("casino.commands.yahtzee.lib.util.heading") as mock_heading:
            lib.menu(_make_args())
            mock_heading.reset_mock()
            mock_ic.call_args.kwargs["help"]()
        self.assertEqual(mock_heading.call_args.args[0], "Yahtzee")


if __name__ == "__main__":
    unittest.main()
