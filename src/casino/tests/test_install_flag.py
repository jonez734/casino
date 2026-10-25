#!/usr/bin/env python3
# casino/tests/test_install_flag.py
# Tests for ``casino --install``: the parser flag and the gates that run
# before casino's startup (bed's engine schema, then the owner check).
# No database is touched; the gates and casino's startup are mocked.

import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")

from casino import __main__ as cm  # noqa: E402
from casino import lib  # noqa: E402


class TestInstallFlag(unittest.TestCase):
    def test_flag_defaults_false(self):
        args = lib.buildargs().parse_args([])
        self.assertFalse(args.install)

    def test_flag_sets_true(self):
        args = lib.buildargs().parse_args(["--install", "--databasename=zoid6test"])
        self.assertTrue(args.install)
        self.assertEqual(args.databasename, "zoid6test")


class TestInstallGates(unittest.TestCase):
    def _args(self):
        return lib.buildargs().parse_args(["--install", "--databasename=zoid6test"])

    def test_refuses_when_bed_engine_schema_missing(self):
        with patch("bed.startup.verify_install", return_value=False), \
                patch("casino.startup.main") as startup:
            rc = cm._run_install(self._args())
        self.assertEqual(rc, 1)
        startup.assert_not_called()

    def test_refuses_non_owner_before_startup(self):
        with patch("bed.startup.verify_install", return_value=True), \
                patch("bbsengine6.database.getpool"), \
                patch("bbsengine6.database.connect"), \
                patch("bbsengine6.backend.checksuperuser.main", return_value=False), \
                patch("casino.startup.main") as startup:
            rc = cm._run_install(self._args())
        self.assertEqual(rc, 1)
        startup.assert_not_called()

    def test_owner_runs_startup_once_and_exits_zero(self):
        with patch("bed.startup.verify_install", return_value=True), \
                patch("bbsengine6.database.getpool"), \
                patch("bbsengine6.database.connect"), \
                patch("bbsengine6.backend.checksuperuser.main", return_value=True), \
                patch("casino.startup.main", return_value=True) as startup:
            rc = cm._run_install(self._args())
        self.assertEqual(rc, 0)
        startup.assert_called_once()

    def test_startup_failure_exits_one(self):
        with patch("bed.startup.verify_install", return_value=True), \
                patch("bbsengine6.database.getpool"), \
                patch("bbsengine6.database.connect"), \
                patch("bbsengine6.backend.checksuperuser.main", return_value=True), \
                patch("casino.startup.main", return_value=False):
            rc = cm._run_install(self._args())
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
