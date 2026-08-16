#!/usr/bin/env python3
# casino/tests/test_slots_commands.py
# Tests for the slots commands shim and the module.run() dispatch flow
# that connects casino.main's "S" Slots menu entry to the local game.
#
# Mirrors tests/test_blackjack_commands.py so future contributors find
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


class TestCommandsSlotsPackage(unittest.TestCase):
    """The commands.slots shim must exist and expose the expected surface."""

    def test_package_importable(self):
        import casino.commands.slots

        self.assertTrue(hasattr(casino.commands.slots, "SUBCOMMANDS"))
        self.assertTrue(hasattr(casino.commands.slots, "main"))
        self.assertTrue(hasattr(casino.commands.slots, "init"))
        self.assertTrue(hasattr(casino.commands.slots, "access"))
        self.assertTrue(hasattr(casino.commands.slots, "buildargs"))

    def test_subcommands_dict_has_play(self):
        from casino.commands.slots import SUBCOMMANDS

        self.assertIn("play", SUBCOMMANDS)
        self.assertTrue(callable(SUBCOMMANDS["play"]))

    def test_lib_exports(self):
        from casino.commands.slots.lib import menu, play

        self.assertTrue(callable(play))
        self.assertTrue(callable(menu))


class TestCommandsSlotsResolveSubcommand(unittest.TestCase):
    """Subcommand prefix resolution for the slots commands shim."""

    def test_exact_match(self):
        from casino.commands.slots import _resolve_subcommand

        self.assertEqual(_resolve_subcommand("play"), "play")

    def test_partial_match(self):
        from casino.commands.slots import _resolve_subcommand

        self.assertEqual(_resolve_subcommand("pl"), "play")

    def test_empty_returns_none(self):
        from casino.commands.slots import _resolve_subcommand

        self.assertIsNone(_resolve_subcommand(""))

    def test_no_match_returns_none(self):
        from casino.commands.slots import _resolve_subcommand

        self.assertIsNone(_resolve_subcommand("xyz"))


class TestCommandsSlotsMainDispatch(unittest.TestCase):
    """commands.slots.main dispatches subcommands via SUBCOMMANDS."""

    def test_no_subcommand_invokes_menu(self):
        from casino.commands.slots import main

        with patch("casino.commands.slots.lib.menu") as mock_menu:
            result = main(_make_args())
        mock_menu.assert_called_once()
        self.assertTrue(result)

    def test_known_subcommand_invokes_callback(self):
        from casino.commands.slots import SUBCOMMANDS, main

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
        from casino.commands.slots import main

        with patch("casino.commands.slots.lib.menu") as mock_menu:
            result = main(_make_args(), subcommand="nonexistent")
        mock_menu.assert_called_once()
        self.assertTrue(result)


class TestPlayUsesModuleRun(unittest.TestCase):
    """commands/slots/lib.py:play() must delegate to module.run() so the
    standard init/buildargs/main flow applies."""

    def test_play_calls_module_run_with_correct_target(self):
        from casino.commands.slots import lib

        sentinel = object()
        with patch("bbsengine6.module.run", return_value=sentinel) as mock_run:
            result = lib.play(_make_args(), extra_kw="value")

        self.assertIs(result, sentinel)
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[1], "game")
        self.assertEqual(kwargs.get("package"), "casino.slots")
        self.assertEqual(kwargs.get("extra_kw"), "value")
        self.assertNotIn(
            "subcommand",
            kwargs,
            "subcommand kwarg is for the commands dispatcher and must not "
            "leak into the inner game module.",
        )


class TestSlotsPackageMainUsesModuleRun(unittest.TestCase):
    """casino.slots.main() must route through module.run() so callers like
    casino.slots.__main__ get the standard machinery (registration,
    buildargs, signature checks)."""

    def test_init_main_delegates_to_module_run(self):
        import casino.slots

        sentinel = object()
        with patch("bbsengine6.module.run", return_value=sentinel) as mock_run:
            result = casino.slots.main(_make_args(), extra_kw="value")

        self.assertIs(result, sentinel)
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[1], "game")
        self.assertEqual(kwargs.get("package"), "casino.slots")
        self.assertEqual(kwargs.get("extra_kw"), "value")


class TestSlotsGameRegistersItself(unittest.TestCase):
    """casino.slots.game.init() must call register_module() so bbsengine6
    recognizes the inner game module."""

    def test_game_init_calls_register_module(self):
        from casino.slots import game

        with patch("casino.slots.game.register_module") as mock_reg:
            result = game.init(_make_args())

        self.assertTrue(result)
        mock_reg.assert_called_once()
        kwargs = mock_reg.call_args.kwargs
        self.assertEqual(kwargs.get("name"), "casino.slots.game")
        self.assertEqual(kwargs.get("module_path"), "casino.slots.game")


class TestModuleCheckPasses(unittest.TestCase):
    """bbsengine6.module.check() must accept the new slots modules."""

    def test_commands_slots_passes(self):
        from bbsengine6 import module

        self.assertTrue(
            module.check(_make_args(), "slots", package="casino.commands")
        )

    def test_slots_package_passes(self):
        from bbsengine6 import module

        self.assertTrue(module.check(_make_args(), "casino.slots"))

    def test_slots_game_passes(self):
        from bbsengine6 import module

        self.assertTrue(
            module.check(_make_args(), "game", package="casino.slots")
        )


class TestSlotsMenuHelpWiring(unittest.TestCase):
    """commands/slots/lib.py:menu() must wire help= so KEY_HELP redraws the
    option list. The help callback must call util.heading() exactly once
    per display of help (one F1 press -> one heading)."""

    def test_menu_passes_help_to_inputchoice(self):
        from casino.commands.slots import lib

        with patch("bbsengine6.io.inputchoice", return_value="q") as mock_ic:
            lib.menu(_make_args())

        mock_ic.assert_called_once()
        kwargs = mock_ic.call_args.kwargs
        self.assertIn("help", kwargs)
        self.assertTrue(callable(kwargs["help"]))

    def test_help_callback_calls_heading_exactly_once(self):
        """Simulate one F1 press: util.heading() must be called exactly once."""
        from casino.commands.slots import lib

        with patch("bbsengine6.io.inputchoice") as mock_ic, \
             patch("casino.commands.slots.lib.util.heading") as mock_heading:
            lib.menu(_make_args())
            mock_heading.reset_mock()
            mock_ic.call_args.kwargs["help"]()
        self.assertEqual(mock_heading.call_count, 1)

    def test_help_callback_uses_slots_heading(self):
        """The heading title must be 'Slots' so F1 shows the right banner."""
        from casino.commands.slots import lib

        with patch("bbsengine6.io.inputchoice") as mock_ic, \
             patch("casino.commands.slots.lib.util.heading") as mock_heading:
            lib.menu(_make_args())
            mock_heading.reset_mock()
            mock_ic.call_args.kwargs["help"]()
        self.assertEqual(mock_heading.call_args.args[0], "Slots")


class TestSlotsPlayHelpWiring(unittest.TestCase):
    """casino/slots/play.py must wire help= on every interactive prompt
    and call util.heading() exactly once per help redraw."""

    def test_bet_help_calls_heading_exactly_once(self):
        from casino.slots import play

        with patch("casino.slots.play.util.heading") as mock_heading:
            play._render_bet_help()
        self.assertEqual(mock_heading.call_count, 1)
        self.assertEqual(mock_heading.call_args.args[0], "play slots")

    def test_again_help_calls_heading_exactly_once(self):
        from casino.slots import play

        with patch("casino.slots.play.util.heading") as mock_heading:
            play._render_again_help()
        self.assertEqual(mock_heading.call_count, 1)
        self.assertEqual(mock_heading.call_args.args[0], "play slots")


class TestEndToEndDispatch(unittest.TestCase):
    """The full path: casino.commands.slots.main (subcommand='play')
    -> commands/slots/lib.py:play() -> module.run('game',
    package='casino.slots') -> casino.slots.game.main."""

    def test_play_subcommand_resolves_game_module(self):
        from bbsengine6 import module

        from casino.slots import game

        m = module.get("game", None, package="casino.slots")
        self.assertIs(m, game)


class TestMainmenuHookup(unittest.TestCase):
    """The main menu entry ('S', 'Slots', 'slots.play') must parse cleanly
    and resolve to a callable subcommand."""

    def test_mainmenu_path_loads(self):
        from casino.commands import slots

        self.assertTrue(hasattr(slots, "main"))
        self.assertTrue(callable(slots.main))

    def test_parse_module_path_yields_slots_play(self):
        from casino.main import parse_module_path

        module, subcommand = parse_module_path("slots.play")
        self.assertEqual(module, "slots")
        self.assertEqual(subcommand, "play")


if __name__ == "__main__":
    unittest.main()
