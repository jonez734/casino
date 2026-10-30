#!/usr/bin/env python3
# casino/tests/test_blackjack_entry_db.py
# Tests for `casino blackjack`: the database settings reach the game, and the
# game opens a pool for its session and member lookups. Database access is
# mocked; nothing connects to a real database.

import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")

from casino import __main__ as cm  # noqa: E402
from casino import lib  # noqa: E402
from casino.blackjack import lib as bj  # noqa: E402

CASINO = Path(__file__).resolve().parents[1]


def _top_args(argv):
    """Parse argv the way casino.main does: top-level parser first."""
    args, remaining = lib.buildargs().parse_known_args(argv)
    return args, remaining


class TestDatabaseFlagsReachBlackjack(unittest.TestCase):
    """The top-level parser consumes --databasename/--databaseuser; the blackjack
    sub-parser never sees them. _run_blackjack must carry them over."""

    def _run_with(self, argv):
        top, remaining = _top_args(argv)
        self.assertEqual(remaining[0], "blackjack")
        captured = {}

        class _Pool:
            def __enter__(self):
                return "POOL"

            def __exit__(self, *a):
                return False

        def fake_getpool(bj_args, **kw):
            captured.setdefault("getpool_args", bj_args)
            return _Pool()

        with patch.object(cm.database, "getpool", side_effect=fake_getpool), \
                patch.object(cm.session, "start") as start, \
                patch.object(cm.bottombar, "init"), \
                patch("bbsengine6.module.run") as run, \
                patch("bbsengine6.bottombar.setbottombar") as setbb, \
                patch.object(cm.io, "echo"), \
                patch.object(cm.io.terminal, "height", return_value=24):
            cm._run_blackjack(top, remaining[1:])
        return captured, start, run, setbb

    def test_databasename_and_user_are_carried_over(self):
        captured, *_ = self._run_with(
            ["--databasename=zoid6test", "--databaseuser=jam", "blackjack"]
        )
        bj_args = captured["getpool_args"]
        self.assertEqual(bj_args.databasename, "zoid6test")
        self.assertEqual(bj_args.databaseuser, "jam")

    def test_unset_flags_keep_blackjack_defaults(self):
        captured, *_ = self._run_with(["blackjack"])
        bj_args = captured["getpool_args"]
        # No top-level override: the blackjack parser's default stands.
        self.assertEqual(bj_args.databasename, "zoid6test")
        self.assertIsNone(bj_args.databaseuser)


class TestSubcommandFlagWins(unittest.TestCase):
    """A database flag after ``blackjack`` overrides the top-level value."""

    def _bj_args(self, argv):
        top, remaining = _top_args(argv)
        captured = {}

        class _Pool:
            def __enter__(self_inner):
                return object()

            def __exit__(self_inner, *a):
                return False

        def fake_getpool(bj_args, **kw):
            captured["args"] = bj_args
            return _Pool()

        with patch.object(cm.database, "getpool", side_effect=fake_getpool), \
                patch.object(cm.session, "start"), \
                patch.object(cm.bottombar, "init"), \
                patch("bbsengine6.module.run"), \
                patch("bbsengine6.bottombar.setbottombar"), \
                patch.object(cm.io, "echo"), \
                patch.object(cm.io.terminal, "height", return_value=24):
            cm._run_blackjack(top, remaining[1:])
        return captured["args"]

    def test_subcommand_database_wins_over_top_level(self):
        bj_args = self._bj_args(
            ["--databasename=zoid6test", "blackjack", "--databasename=bjdb"]
        )
        self.assertEqual(bj_args.databasename, "bjdb")

    def test_top_level_applies_when_subcommand_is_silent(self):
        bj_args = self._bj_args(["--databasename=zoid6test", "blackjack"])
        self.assertEqual(bj_args.databasename, "zoid6test")


class TestPoolIsPassedToSessionAndGame(unittest.TestCase):
    def _run(self, argv=("--databasename=zoid6test", "--databaseuser=jam", "blackjack")):
        top, remaining = _top_args(list(argv))
        pools = []

        # The entry point takes the cached pool from getpool and does not enter it, so record
        # what getpool hands out. The game must receive that same object.
        class _Pool:
            pass

        def fake_getpool(*a, **kw):
            pool = _Pool()
            pools.append(pool)
            return pool

        with patch.object(cm.database, "getpool", side_effect=fake_getpool), \
                patch.object(cm.session, "start") as start, \
                patch.object(cm.bottombar, "init"), \
                patch("bbsengine6.module.run") as run, \
                patch("bbsengine6.bottombar.setbottombar") as setbb, \
                patch.object(cm.io, "echo"), \
                patch.object(cm.io.terminal, "height", return_value=24):
            cm._run_blackjack(top, remaining[1:])
        return start, run, setbb, pools

    def test_session_start_receives_a_pool(self):
        start, _, _, _ = self._run()
        start.assert_called_once()
        self.assertIn("pool", start.call_args.kwargs)
        self.assertIsNotNone(start.call_args.kwargs["pool"])

    def test_game_run_receives_the_same_pool(self):
        _, run, _, pools = self._run()
        run.assert_called_once()
        self.assertIn("pool", run.call_args.kwargs)
        self.assertIs(run.call_args.kwargs["pool"], pools[-1])

    def test_bottombar_context_is_set_with_blackjack_args(self):
        _, _, setbb, _ = self._run()
        setbb.assert_called_once()
        bb_args = setbb.call_args.args[0]
        self.assertEqual(bb_args.databasename, "zoid6test")
        self.assertEqual(bb_args.databaseuser, "jam")


class TestGameLooksUpMemberWithPool(unittest.TestCase):
    def test_game_main_passes_pool_to_getcurrentmoniker(self):
        from casino.blackjack import game

        pool = object()
        args = argparse.Namespace(debug=False, databasename="zoid6test")

        with patch.object(game, "member") as member, \
                patch.object(game, "lib") as lib_mod, \
                patch.object(game, "libcasino") as libcasino, \
                patch.object(game, "io") as io_mod:
            member.getcurrentmoniker.return_value = "testplayer"
            lib_mod.BlackjackPlayer.return_value = MagicMock()
            libcasino.Shoe.return_value = MagicMock()
            io_mod.inputboolean.return_value = False
            game.main(args, pool=pool)

        member.getcurrentmoniker.assert_called_once()
        self.assertIs(member.getcurrentmoniker.call_args.kwargs["pool"], pool)


class TestGameSourceUsesPool(unittest.TestCase):
    """Source-level guard, in the style of test_no_removed_member_getcurrentid."""

    def test_game_passes_pool_kwarg(self):
        src = (CASINO / "blackjack" / "game.py").read_text()
        self.assertIn("getcurrentmoniker(args, pool=kw.get(\"pool\"))", src)

    def test_entry_point_opens_a_pool_for_session_and_game(self):
        src = (CASINO / "__main__.py").read_text()
        body = src[src.index("def _run_blackjack"):src.index("_BLACKJACK_SUBCOMMAND =")]
        # The entry point opens its pool through the process pool helper, once per scope.
        self.assertGreaterEqual(body.count("context_pool("), 2)
        self.assertIn("session.start(bj_args, pool=pool)", body)
        self.assertIn('package="casino.blackjack", pool=pool', body)


if __name__ == "__main__":
    unittest.main()
