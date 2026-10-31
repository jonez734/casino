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
import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from bbsengine6 import bottombar

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")


def _make_args(**overrides) -> argparse.Namespace:
    args = argparse.Namespace()
    args.verbose = False
    args.debug = False
    args.databasename = "zoid6test"
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

    def test_buildargs_registers_bed_flags(self):
        from casino.lib import buildargs

        parser = buildargs()
        ns, _ = parser.parse_known_args(
            [
                "--bed-host", "h",
                "--bed-port", "9999",
                "--bed-path", "/ws",
                "--bed-call-timeout", "7.0",
                "--bed-probe-timeout", "0.5",
            ]
        )
        self.assertEqual(ns.bed_host, "h")
        self.assertEqual(ns.bed_port, 9999)
        self.assertEqual(ns.bed_path, "/ws")
        self.assertEqual(ns.bed_call_timeout, 7.0)
        self.assertEqual(ns.bed_probe_timeout, 0.5)

    def test_direct_flag_is_not_recognised(self):
        """Casino has no door mode: --direct is not a parsed option, so it is left over."""
        from casino.lib import buildargs

        parser = buildargs()
        ns, leftover = parser.parse_known_args(["--direct"])
        self.assertIn("--direct", leftover)
        self.assertFalse(hasattr(ns, "direct"))

    def test_buildargs_defaults(self):
        from casino.lib import buildargs

        parser = buildargs()
        ns, _ = parser.parse_known_args([])
        self.assertEqual(ns.bed_host, "localhost")
        self.assertEqual(ns.bed_port, 8765)
        self.assertEqual(ns.bed_path, "/")
        self.assertEqual(ns.bed_call_timeout, 5.0)
        self.assertEqual(ns.bed_probe_timeout, 0.25)


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


class _NoopPool:
    """Stands in for a database pool in the blackjack dispatch tests."""

    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


class TestMainDispatchVersionAndHelp(unittest.TestCase):
    """``--version`` and ``--help`` must not require a bed connection.

    argparse's ``action="version"`` (and the default ``--help`` action)
    short-circuits inside ``parse_known_args`` via ``parser.exit()``,
    so the dispatcher must never reach ``_routing.select_backend`` or
    ``probe_bed``. Regression test for the bug where ``casino --version``
    raised :class:`bed.tools._routing.BedNotReachable` because ``--version``
    was not a registered action and slipped into ``remaining_argv``.
    """

    def test_version_action_does_not_probe_bed(self):
        from casino.__main__ import main

        with patch("casino._routing.probe_bed") as probe, \
             patch("casino._routing.select_backend") as sel:
            with self.assertRaises(SystemExit) as ctx:
                main(["--version"])
            self.assertEqual(ctx.exception.code, 0)
        probe.assert_not_called()
        sel.assert_not_called()

    def test_help_action_does_not_probe_bed(self):
        from casino.__main__ import main

        for flag in ("--help", "-h"):
            with patch("casino._routing.probe_bed") as probe, \
                 patch("casino._routing.select_backend") as sel:
                with self.assertRaises(SystemExit) as ctx:
                    main([flag])
                self.assertEqual(ctx.exception.code, 0)
            probe.assert_not_called()
            sel.assert_not_called()

    def test_parser_prints_canonical_version(self):
        """The version string is sourced from ``casino._version``.

        Pins the contract that ``--version`` advertises the
        setuptools-scm-managed version (the same one
        ``pyproject.toml`` reads via ``tool.setuptools.dynamic.version``)
        rather than the legacy ``casino.__init__.__version__`` literal.
        """
        from casino import _version as casino_version
        from casino.lib import buildargs

        parser = buildargs()
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as ctx:
            parser.parse_known_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        output = buf.getvalue().strip()
        self.assertIn("casino", output)
        self.assertIn(casino_version.version, output)


class _StubParser:
    """Minimal parser stand-in for tests that want to inject a fixed Namespace."""

    def __init__(self, args: argparse.Namespace, leftover: list | None = None) -> None:
        self._args = args
        self._leftover = leftover or []

    def parse_known_args(self, argv: list) -> tuple[argparse.Namespace, list]:
        return self._args, list(self._leftover)


if __name__ == "__main__":
    unittest.main()
