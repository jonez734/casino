#!/usr/bin/env python3
# casino/tests/test_blackjack_commands.py
# Tests for the blackjack commands shim and the module.run() dispatch flow
# that connects casino.main's "B" Blackjack menu entry to the local game.

import argparse
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


def _make_args(**overrides) -> argparse.Namespace:
    base = {"debug": False}
    base.update(overrides)
    return argparse.Namespace(**base)


class TestCommandsBlackjackPackage(unittest.TestCase):
    """The commands.blackjack shim must exist and expose the expected surface."""

    def test_package_importable(self):
        import casino.commands.blackjack

        self.assertTrue(hasattr(casino.commands.blackjack, "SUBCOMMANDS"))
        self.assertTrue(hasattr(casino.commands.blackjack, "main"))
        self.assertTrue(hasattr(casino.commands.blackjack, "init"))
        self.assertTrue(hasattr(casino.commands.blackjack, "access"))
        self.assertTrue(hasattr(casino.commands.blackjack, "buildargs"))

    def test_subcommands_dict_has_play(self):
        from casino.commands.blackjack import SUBCOMMANDS

        self.assertIn("play", SUBCOMMANDS)
        self.assertTrue(callable(SUBCOMMANDS["play"]))

    def test_lib_exports(self):
        from casino.commands.blackjack.lib import menu, play

        self.assertTrue(callable(play))
        self.assertTrue(callable(menu))


class TestCommandsBlackjackResolveSubcommand(unittest.TestCase):
    """Subcommand prefix resolution for the blackjack commands shim."""

    def test_exact_match(self):
        from casino.commands.blackjack import _resolve_subcommand

        self.assertEqual(_resolve_subcommand("play"), "play")

    def test_partial_match(self):
        from casino.commands.blackjack import _resolve_subcommand

        self.assertEqual(_resolve_subcommand("pl"), "play")

    def test_empty_returns_none(self):
        from casino.commands.blackjack import _resolve_subcommand

        self.assertIsNone(_resolve_subcommand(""))

    def test_no_match_returns_none(self):
        from casino.commands.blackjack import _resolve_subcommand

        self.assertIsNone(_resolve_subcommand("xyz"))


class TestCommandsBlackjackMainDispatch(unittest.TestCase):
    """commands.blackjack.main dispatches subcommands via SUBCOMMANDS."""

    def test_no_subcommand_invokes_menu(self):
        from casino.commands.blackjack import main

        with patch("casino.commands.blackjack.lib.menu") as mock_menu:
            result = main(_make_args())
        mock_menu.assert_called_once()
        self.assertTrue(result)

    def test_known_subcommand_invokes_callback(self):
        from casino.commands.blackjack import SUBCOMMANDS, main

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
        from casino.commands.blackjack import main

        with patch("casino.commands.blackjack.lib.menu") as mock_menu:
            result = main(_make_args(), subcommand="nonexistent")
        mock_menu.assert_called_once()
        self.assertTrue(result)


class TestPlayUsesModuleRun(unittest.TestCase):
    """commands/blackjack/lib.py:play() must delegate to module.run() so the
    standard init/buildargs/main flow applies. Direct calls to game.main()
    or to lib.runmodule() bypass registration and signature checks."""

    def test_play_calls_module_run_with_correct_target(self):
        from casino.commands.blackjack import lib

        sentinel = object()
        with patch("bbsengine6.module.run", return_value=sentinel) as mock_run:
            result = lib.play(_make_args(), extra_kw="value")

        self.assertIs(result, sentinel)
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[1], "game")
        self.assertEqual(kwargs.get("package"), "casino.blackjack")
        self.assertEqual(kwargs.get("extra_kw"), "value")
        self.assertNotIn(
            "subcommand",
            kwargs,
            "subcommand kwarg is for the commands dispatcher and must not "
            "leak into the inner game module.",
        )


class TestBlackjackPackageMainUsesModuleRun(unittest.TestCase):
    """casino.blackjack.__init__.main() must also route through module.run()
    so callers like casino.blackjack.__main__ or future entry points get the
    standard machinery (registration, buildargs, signature checks)."""

    def test_init_main_delegates_to_module_run(self):
        import casino.blackjack

        sentinel = object()
        with patch("bbsengine6.module.run", return_value=sentinel) as mock_run:
            result = casino.blackjack.main(_make_args(), extra_kw="value")

        self.assertIs(result, sentinel)
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[1], "game")
        self.assertEqual(kwargs.get("package"), "casino.blackjack")
        self.assertEqual(kwargs.get("extra_kw"), "value")


class TestModuleCheckPasses(unittest.TestCase):
    """bbsengine6.module.check() must accept the new and existing blackjack
    modules now that the signature validation is correctly returning False
    on mismatch and the stubs are aligned with the conventional
    ``def main(args, **kw)`` style."""

    def test_commands_blackjack_passes(self):
        from bbsengine6 import module

        self.assertTrue(
            module.check(_make_args(), "blackjack", package="casino.commands")
        )

    def test_blackjack_package_passes(self):
        from bbsengine6 import module

        self.assertTrue(module.check(_make_args(), "casino.blackjack"))

    def test_blackjack_game_passes(self):
        from bbsengine6 import module

        self.assertTrue(
            module.check(_make_args(), "game", package="casino.blackjack")
        )


class TestSignatureCheckReturnsFalse(unittest.TestCase):
    """Regression: the inner ``fail()`` used to return a truthy SignatureError
    instance, so ``if not _check_func_signature(...)`` never triggered and
    every mismatch silently passed. It must now return False."""

    def test_kind_mismatch_returns_false(self):
        from bbsengine6 import module

        def stub(args, /, **kwargs):
            pass

        def func(args, **kw):
            pass

        self.assertFalse(module._check_func_signature(func, stub))

    def test_too_few_params_returns_false(self):
        from bbsengine6 import module

        def stub(a, b, /, **kwargs):
            pass

        def func(a, /, **kwargs):
            pass

        self.assertFalse(module._check_func_signature(func, stub))

    def test_matching_signature_returns_true(self):
        from bbsengine6 import module

        def stub(args, /, **kwargs):
            pass

        def func(args, /, **kwargs):
            pass

        self.assertTrue(module._check_func_signature(func, stub))

    def test_variadic_name_difference_is_ok(self):
        """``**kw`` and ``**kwargs`` are equivalent at the call site; the
        check should not reject either form against a stub that uses the
        other."""

        from bbsengine6 import module

        def stub(args, /, **kwargs):
            pass

        def func_kw(args, /, **kw):
            pass

        def func_kwargs(args, /, **kwargs):
            pass

        self.assertTrue(module._check_func_signature(func_kw, stub))
        self.assertTrue(module._check_func_signature(func_kwargs, stub))

    def test_narrower_return_type_against_union_accepted(self):
        """``bool`` should be accepted against a ``bool | None`` stub."""

        from bbsengine6 import module

        def stub() -> bool | None:
            pass

        def func() -> bool:
            return True

        self.assertTrue(module._check_func_signature(func, stub))


class TestBlackjackPlayer(unittest.TestCase):
    """casino.blackjack.lib.BlackjackPlayer initialises a blackjack-specific
    stats bucket with the expected counters."""

    def test_stats_bucket_initialised(self):
        from casino.blackjack.lib import BlackjackPlayer

        p = BlackjackPlayer()
        self.assertIn("blackjack", p.stats)
        bucket = p.stats["blackjack"]
        for key in ("win", "loss", "draw", "bust", "blackjack", "naturalblackjack"):
            self.assertEqual(bucket.get(key), 0)

    def test_incstat_uses_blackjack_namespace(self):
        """incstat takes a single ``stat`` argument and is responsible for
        namespacing it under the ``blackjack`` stats bucket when delegating
        to the parent Player."""

        from casino.blackjack.lib import BlackjackPlayer

        p = BlackjackPlayer()
        with patch.object(p, "incstat", wraps=p.incstat) as spy:
            p.incstat("win")
        spy.assert_called_once_with("win")


class TestEndToEndDispatch(unittest.TestCase):
    """The full path: casino.commands.blackjack.main (subcommand='play')
    -> commands/blackjack/lib.py:play() -> module.run('game',
    package='casino.blackjack') -> casino.blackjack.game.main."""

    def test_play_subcommand_resolves_game_module(self):
        from bbsengine6 import module
        from casino.blackjack import game

        # Verify the resolution path the new dispatch relies on.
        m = module.get("game", None, package="casino.blackjack")
        self.assertIs(m, game)


class TestMainmenuHookup(unittest.TestCase):
    """The main menu entry ``("B", "Blackjack", "blackjack.play")`` must
    parse cleanly and resolve to a callable subcommand. This guards against
    the original regression where pressing B crashed with
    ``ModuleNotFoundError: No module named 'casino.commands.blackjack'``."""

    def test_mainmenu_path_loads(self):
        from casino.commands import blackjack

        self.assertTrue(hasattr(blackjack, "main"))
        self.assertTrue(callable(blackjack.main))

    def test_parse_module_path_yields_blackjack_play(self):
        from casino.main import parse_module_path

        module, subcommand = parse_module_path("blackjack.play")
        self.assertEqual(module, "blackjack")
        self.assertEqual(subcommand, "play")


if __name__ == "__main__":
    unittest.main()
