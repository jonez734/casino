#!/usr/bin/env python3
# casino/tests/test_main_dispatch.py
# Tests for the merged ``casino`` CLI dispatcher (``casino.__main__:main``).
#
# The dispatcher picks one of two branches:
#
# - ``--direct``: door mode. Opens a DB pool via ``bbsengine6.database``,
#   starts a BBS session, runs ``casino.main`` (the interactive menu).
# - default: bed WebSocket client. Probes the bed daemon on
#   ``--bed-host/--bed-port``; if reachable, instantiates ``CasinoClient``
#   and runs the terminal UI loop. If unreachable, raises
#   :class:`bed.tools._routing.BedNotReachable`.

import argparse
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")


def _make_args(**overrides) -> argparse.Namespace:
    args = argparse.Namespace()
    args.verbose = False
    args.debug = False
    args.databasename = "zoid6"
    args.databasehost = "localhost"
    args.databaseuser = None
    args.databaseport = 5432
    args.databasepassword = None
    args.bed_host = "localhost"
    args.bed_port = 8765
    args.bed_path = "/"
    args.bed_call_timeout = 5.0
    args.bed_probe_timeout = 0.25
    args.direct = False
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


class TestMainParserShape(unittest.TestCase):
    """``casino.lib.buildargs()`` registers the merged CLI's flags."""

    def test_buildargs_registers_bed_and_direct_flags(self):
        from casino.lib import buildargs

        parser = buildargs()
        ns, _ = parser.parse_known_args(
            [
                "--bed-host", "h",
                "--bed-port", "9999",
                "--bed-path", "/ws",
                "--bed-call-timeout", "7.0",
                "--bed-probe-timeout", "0.5",
                "--direct",
            ]
        )
        self.assertEqual(ns.bed_host, "h")
        self.assertEqual(ns.bed_port, 9999)
        self.assertEqual(ns.bed_path, "/ws")
        self.assertEqual(ns.bed_call_timeout, 7.0)
        self.assertEqual(ns.bed_probe_timeout, 0.5)
        self.assertTrue(ns.direct)

    def test_buildargs_defaults(self):
        from casino.lib import buildargs

        parser = buildargs()
        ns, _ = parser.parse_known_args([])
        self.assertEqual(ns.bed_host, "localhost")
        self.assertEqual(ns.bed_port, 8765)
        self.assertEqual(ns.bed_path, "/")
        self.assertEqual(ns.bed_call_timeout, 5.0)
        self.assertEqual(ns.bed_probe_timeout, 0.25)
        self.assertFalse(ns.direct)


class TestMainDispatchBedUnreachable(unittest.TestCase):
    """Default branch with bed unreachable: BedNotReachable propagates."""

    def test_default_branch_with_unreachable_bed_raises(self):
        from bed.tools._routing import BedNotReachable

        from casino.__main__ import main

        args = _make_args(bed_host="nope.example", bed_port=9999)

        with patch("casino._routing.probe_bed", return_value=False), \
             patch("casino._routing.build_client_args"), \
             patch("casino.lib.buildargs", return_value=_StubParser(args)):
            with self.assertRaises(BedNotReachable) as ctx:
                main([])
            self.assertIn("--direct", str(ctx.exception))
            self.assertIn("nope.example", str(ctx.exception))
            self.assertIn("9999", str(ctx.exception))


class TestMainDispatchBedReachable(unittest.TestCase):
    """Default branch with bed reachable: CasinoClient.run() is called."""

    def test_default_branch_runs_casino_client(self):
        from casino.__main__ import main

        args = _make_args()
        fake_client = MagicMock()
        fake_client.authenticated = True

        with patch("casino._routing.probe_bed", return_value=True), \
             patch("casino._routing.build_client_args"), \
             patch("casino.lib.buildargs", return_value=_StubParser(args)), \
             patch("casino.__main__.CasinoClient", return_value=fake_client) as MockClient:
            rc = main([])

        self.assertEqual(rc, 0)
        MockClient.assert_called_once_with(args)
        fake_client.run.assert_called_once()

    def test_default_branch_returns_one_when_not_authenticated(self):
        from casino.__main__ import main

        args = _make_args()
        fake_client = MagicMock()
        fake_client.authenticated = False

        with patch("casino._routing.probe_bed", return_value=True), \
             patch("casino._routing.build_client_args"), \
             patch("casino.lib.buildargs", return_value=_StubParser(args)), \
             patch("casino.__main__.CasinoClient", return_value=fake_client):
            rc = main([])

        self.assertEqual(rc, 1)


class TestMainDispatchDirect(unittest.TestCase):
    """--direct branch: door mode is invoked; no CasinoClient is constructed."""

    def test_direct_branch_runs_door_mode(self):
        from casino.__main__ import main

        args = _make_args(direct=True)

        with patch("casino._routing.select_backend", return_value="direct") as sel, \
             patch("casino._routing.build_client_args"), \
             patch("casino.lib.buildargs", return_value=_StubParser(args)), \
             patch("casino.__main__._run_direct", return_value=0) as run_direct, \
             patch("casino.__main__.CasinoClient") as MockClient:
            rc = main([])

        self.assertEqual(rc, 0)
        sel.assert_called_once_with(args)
        run_direct.assert_called_once()
        MockClient.assert_not_called()

    def test_direct_branch_passes_remaining_argv(self):
        from casino.__main__ import main

        args = _make_args(direct=True)

        with patch("casino._routing.select_backend", return_value="direct"), \
             patch("casino._routing.build_client_args"), \
             patch("casino.lib.buildargs", return_value=_StubParser(args, leftover=["foo", "bar"])), \
             patch("casino.__main__._run_direct", return_value=0) as run_direct, \
             patch("casino.__main__.CasinoClient"):
            main(["foo", "bar"])

        run_direct.assert_called_once_with(args, ["foo", "bar"])


class TestMainDispatchBlackjackSubcommand(unittest.TestCase):
    """``casino blackjack [...]`` short-circuits before any backend probe.

    Blackjack has no bed counterpart -- it is door-mode only. The
    dispatcher must skip ``_routing.select_backend`` and ``probe_bed``
    on the blackjack branch, otherwise an unreachable bed daemon would
    block the door-mode startup.
    """

    def test_blackjack_subcommand_skips_bed_probe(self):
        from casino.__main__ import main

        args = _make_args()

        with patch("casino._routing.probe_bed") as probe, \
             patch("casino._routing.select_backend") as sel, \
             patch("casino._routing.build_client_args"), \
             patch("casino.lib.buildargs", return_value=_StubParser(args, leftover=["blackjack"])), \
             patch("bbsengine6.session.start") as session_start, \
             patch("bbsengine6.screen.init"), \
             patch("bbsengine6.module.run") as module_run, \
             patch("bbsengine6.io.echo"), \
             patch("bbsengine6.io.terminal") as terminal, \
             patch("locale.setlocale"), \
             patch("time.tzset"), \
             patch("casino.__main__.CasinoClient") as MockClient:
            terminal.height.return_value = 24
            rc = main(["blackjack"])

        self.assertEqual(rc, 0)
        probe.assert_not_called()
        sel.assert_not_called()
        MockClient.assert_not_called()
        session_start.assert_called_once()
        module_run.assert_called_once()

    def test_blackjack_subcommand_passes_remaining_argv(self):
        """Args after ``blackjack`` flow into casino.blackjack.lib.buildargs()."""
        from casino.__main__ import main

        args = _make_args()

        with patch("casino._routing.probe_bed") as probe, \
             patch("casino._routing.select_backend") as sel, \
             patch("casino._routing.build_client_args"), \
             patch("casino.lib.buildargs", return_value=_StubParser(args, leftover=["blackjack", "--databasename", "bjdb"])), \
             patch("bbsengine6.session.start") as session_start, \
             patch("bbsengine6.screen.init"), \
             patch("bbsengine6.module.run") as module_run, \
             patch("bbsengine6.io.echo"), \
             patch("bbsengine6.io.terminal") as terminal, \
             patch("locale.setlocale"), \
             patch("time.tzset"), \
             patch("casino.__main__.CasinoClient"):
            terminal.height.return_value = 24
            rc = main(["blackjack", "--databasename", "bjdb"])

        self.assertEqual(rc, 0)
        probe.assert_not_called()
        sel.assert_not_called()

        bj_args = session_start.call_args[0][0]
        self.assertEqual(bj_args.databasename, "bjdb")

        module_args = module_run.call_args[0][0]
        self.assertEqual(module_args.databasename, "bjdb")
        self.assertEqual(module_run.call_args.kwargs.get("package"), "casino.blackjack")


class _StubParser:
    """Minimal parser stand-in for tests that want to inject a fixed Namespace."""

    def __init__(self, args: argparse.Namespace, leftover: list | None = None) -> None:
        self._args = args
        self._leftover = leftover or []

    def parse_known_args(self, argv: list) -> tuple[argparse.Namespace, list]:
        return self._args, list(self._leftover)


if __name__ == "__main__":
    unittest.main()
