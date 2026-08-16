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


class TestYahtzeePlayHonoursDirectFlag(unittest.TestCase):
    """commands/yahtzee/lib.py:play() must route to yahtzee/play.py when
    args.direct is True (door-mode), else to yahtzee/game.py (BED-side)."""

    def test_no_direct_flag_routes_to_game_module(self):
        """Default flow (BED-side primary) must land in yahtzee/game.py."""
        from casino.commands.yahtzee import lib

        sentinel = object()
        with patch("bbsengine6.module.run", return_value=sentinel) as mock_run:
            result = lib.play(_make_args(), extra_kw="value")

        self.assertIs(result, sentinel)
        mock_run.assert_called_once()
        args_, kwargs = mock_run.call_args
        self.assertEqual(args_[1], "game")
        self.assertEqual(kwargs.get("package"), "casino.yahtzee")
        self.assertEqual(kwargs.get("extra_kw"), "value")
        self.assertFalse(getattr(args_[0], "direct", False))
        self.assertNotIn(
            "subcommand",
            kwargs,
            "subcommand kwarg is for the commands dispatcher and must not "
            "leak into the inner game module.",
        )

    def test_direct_flag_routes_to_play_module(self):
        """Door-mode (--direct) must land in yahtzee/play.py."""
        from casino.commands.yahtzee import lib

        sentinel = object()
        with patch("bbsengine6.module.run", return_value=sentinel) as mock_run:
            result = lib.play(_make_args(direct=True), extra_kw="value")

        self.assertIs(result, sentinel)
        mock_run.assert_called_once()
        args_, kwargs = mock_run.call_args
        self.assertEqual(args_[1], "play")
        self.assertEqual(kwargs.get("package"), "casino.yahtzee")
        self.assertEqual(kwargs.get("extra_kw"), "value")
        self.assertTrue(args_[0].direct)


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

    def test_yahtzee_play_passes(self):
        from bbsengine6 import module

        self.assertTrue(
            module.check(_make_args(), "play", package="casino.yahtzee")
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

    def test_main_delegates_to_play_with_player_and_dealer(self):
        from casino.yahtzee import game
        from casino.yahtzee import play as yahtzee_play

        sentinel = object()
        with patch.object(
            yahtzee_play, "main", return_value=sentinel
        ) as mock_play, patch.object(game, "member") as mock_member:
            mock_member.getcurrentid.return_value = "alice"
            result = game.main(_make_args(), credits=500, bet_amount=50)

        self.assertIs(result, sentinel)
        mock_play.assert_called_once()
        _, kwargs = mock_play.call_args
        player = kwargs.get("player")
        dealer = kwargs.get("dealer")
        self.assertIsNotNone(player)
        self.assertIsNotNone(dealer)
        self.assertEqual(player.moniker, "alice")
        self.assertEqual(player.credits, 500)
        self.assertEqual(player.bet_amount, 50)
        from casino.yahtzee.dealer import YahtzeeDealer

        self.assertIsInstance(dealer, YahtzeeDealer)


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


class TestYahtzeePlayHelpWiring(unittest.TestCase):
    """casino/yahtzee/play.py must wire help= on every interactive prompt
    and call util.heading() exactly once per help redraw. The action
    prompt heading is 'play yahtzee'; the score-category prompt heading
    is 'score category'."""

    def test_action_help_calls_heading_exactly_once(self):
        from casino.yahtzee import play

        with patch("casino.yahtzee.play.util.heading") as mock_heading:
            play._render_action_help()
        self.assertEqual(mock_heading.call_count, 1)
        self.assertEqual(mock_heading.call_args.args[0], "play yahtzee")

    def test_score_help_calls_heading_exactly_once(self):
        from casino.yahtzee import play

        with patch("casino.yahtzee.play.util.heading") as mock_heading:
            play._render_score_help()
        self.assertEqual(mock_heading.call_count, 1)
        self.assertEqual(mock_heading.call_args.args[0], "score category")

    def test_action_prompt_passes_help_to_inputchoice(self):
        """Each io.inputchoice call in the action prompt must receive help=."""
        from casino.yahtzee import play
        from casino.yahtzee.dealer import YahtzeeDealer
        from casino.yahtzee.player import YahtzeePlayer

        player = YahtzeePlayer(
            moniker="alice", credits=100, bet_amount=10
        )
        dealer = YahtzeeDealer()
        with patch(
            "casino.yahtzee.play.io.inputchoice", return_value="Q"
        ) as mock_ic, patch(
            "casino.yahtzee.play._render_action_help"
        ):
            play._prompt_action(player, dealer)

        self.assertGreaterEqual(mock_ic.call_count, 1)
        kwargs = mock_ic.call_args.kwargs
        self.assertIn("help", kwargs)
        self.assertTrue(callable(kwargs["help"]))

    def test_score_prompt_passes_help_to_inputchoice(self):
        from casino.yahtzee import play
        from casino.yahtzee.player import YahtzeePlayer

        player = YahtzeePlayer(
            moniker="alice", credits=100, bet_amount=10
        )
        with patch(
            "casino.yahtzee.play.io.inputchoice", return_value="c"
        ) as mock_ic, patch(
            "casino.yahtzee.play._render_score_help"
        ):
            play._prompt_score_category(player)

        mock_ic.assert_called_once()
        kwargs = mock_ic.call_args.kwargs
        self.assertIn("help", kwargs)
        self.assertTrue(callable(kwargs["help"]))


class TestYahtzeePlayBuildsFreshWhenNoKwargs(unittest.TestCase):
    """When --direct dispatches straight to casino.yahtzee.play.main (no
    game.py setup), play.main must build a fresh YahtzeePlayer + YahtzeeDealer
    from the kwargs it does receive."""

    def test_main_builds_player_when_not_provided(self):
        from casino.yahtzee import play

        with patch(
            "casino.yahtzee.play.io.inputchoice", side_effect=["Q"]
        ), patch("casino.yahtzee.play.util.heading"):
            result = play.main(
                _make_args(direct=True),
                moniker="bob",
                credits=200,
                bet_amount=25,
            )

        self.assertTrue(result)


class TestMainmenuHookup(unittest.TestCase):
    """The main menu entry ('Y', 'Yahtzee', 'yahtzee.play') must parse cleanly
    and resolve to a callable subcommand."""

    def test_mainmenu_path_loads(self):
        from casino.commands import yahtzee

        self.assertTrue(hasattr(yahtzee, "main"))
        self.assertTrue(callable(yahtzee.main))

    def test_parse_module_path_yields_yahtzee_play(self):
        from casino.main import parse_module_path

        module, subcommand = parse_module_path("yahtzee.play")
        self.assertEqual(module, "yahtzee")
        self.assertEqual(subcommand, "play")


if __name__ == "__main__":
    unittest.main()
