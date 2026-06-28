#!/usr/bin/env python3
# casino/tests/test_client_cli.py
# Tests for the casino-client console-script entry point.

import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestClientCliParser(unittest.TestCase):
    """Argument parser shape and defaults."""

    def test_parser_defaults(self):
        from casino.client_cli import build_parser
        parser = build_parser()
        args = parser.parse_args([])
        self.assertEqual(args.host, "localhost")
        self.assertEqual(args.port, 8765)

    def test_parser_explicit_host_port(self):
        from casino.client_cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["--host", "10.0.0.1", "--port", "9999"])
        self.assertEqual(args.host, "10.0.0.1")
        self.assertEqual(args.port, 9999)


class TestClientCliMain(unittest.TestCase):
    """main() wires the args into CasinoClient.run() and returns POSIX exit codes."""

    def test_help_returns_zero(self):
        from casino.client_cli import main
        with self.assertRaises(SystemExit) as ctx:
            main(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_returns_zero_when_authenticated(self):
        from casino import client_cli

        fake = MagicMock()
        fake.authenticated = True
        with patch("casino.client_cli.CasinoClient", return_value=fake) as MockClient:
            rc = client_cli.main(["--host", "h", "--port", "1"])
        self.assertEqual(rc, 0)
        MockClient.assert_called_once()
        args = MockClient.call_args.args[0]
        self.assertEqual(args.host, "h")
        self.assertEqual(args.port, 1)
        fake.run.assert_called_once()

    def test_returns_one_when_not_authenticated(self):
        from casino import client_cli

        fake = MagicMock()
        fake.authenticated = False
        with patch("casino.client_cli.CasinoClient", return_value=fake):
            rc = client_cli.main([])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
