#!/usr/bin/env python3
# casino/tests/test_commands.py
# Tests for casino commands subpackage

import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestCommandExports(unittest.TestCase):
    """Verify all commands are exported correctly."""

    def test_table_exports(self):
        from casino.commands.table.lib import (
            list_tables,
            create_table,
            update_table,
            join_table,
            leave_table,
            view_table,
            menu,
        )

        self.assertTrue(callable(list_tables))
        self.assertTrue(callable(create_table))
        self.assertTrue(callable(menu))

    def test_game_exports(self):
        from casino.commands.game.lib import (
            bet,
            hit,
            stand,
            game_action,
            play,
            menu,
        )

        self.assertTrue(callable(bet))
        self.assertTrue(callable(hit))
        self.assertTrue(callable(play))

    def test_chat_exports(self):
        from casino.commands.chat.lib import chat, table_chat, menu

        self.assertTrue(callable(chat))
        self.assertTrue(callable(table_chat))

    def test_bank_exports(self):
        from casino.commands.bank.lib import (
            bank_balance,
            bank_add,
            bank_remove,
            bank_transfer,
            bank_approve,
            bank_reject,
            bank_pending,
            bank_history,
            bank_list_all,
            menu,
        )

        self.assertTrue(callable(menu))
        self.assertTrue(callable(bank_balance))

    def test_admin_exports(self):
        from casino.commands.admin.lib import watch_table, unwatch_table, menu

        self.assertTrue(callable(watch_table))
        self.assertTrue(callable(unwatch_table))


class TestSubcommandResolution(unittest.TestCase):
    """Test subcommand resolution in each module."""

    def test_table_resolve_exact(self):
        from casino.commands.table import _resolve_subcommand

        result = _resolve_subcommand("list")
        self.assertEqual(result, "list")

    def test_table_resolve_partial(self):
        from casino.commands.table import _resolve_subcommand

        result = _resolve_subcommand("lis")
        self.assertEqual(result, "list")

    def test_table_resolve_ambiguous(self):
        from casino.commands.table import _resolve_subcommand

        # "l" could match "list" or "leave" - should return None and print error
        with patch("casino.commands.table.io") as mock_io:
            result = _resolve_subcommand("l")
            self.assertIsNone(result)
            mock_io.echo.assert_called_once()

    def test_table_resolve_no_match(self):
        from casino.commands.table import _resolve_subcommand

        result = _resolve_subcommand("xyz")
        self.assertIsNone(result)

    def test_game_resolve_exact(self):
        from casino.commands.game import _resolve_subcommand

        result = _resolve_subcommand("hit")
        self.assertEqual(result, "hit")

    def test_game_resolve_partial(self):
        from casino.commands.game import _resolve_subcommand

        result = _resolve_subcommand("h")
        self.assertEqual(result, "hit")

    def test_game_resolve_ambiguous(self):
        from casino.commands.game import _resolve_subcommand

        # "s" is now ambiguous (stand, split)
        result = _resolve_subcommand("s")
        self.assertIsNone(result)

        # "st" uniquely matches "stand"
        result = _resolve_subcommand("st")
        self.assertEqual(result, "stand")

    def test_chat_resolve_exact(self):
        from casino.commands.chat import _resolve_subcommand

        result = _resolve_subcommand("global")
        self.assertEqual(result, "global")

    def test_bank_resolve_exact(self):
        from casino.commands.bank import _resolve_subcommand

        result = _resolve_subcommand("balance")
        self.assertEqual(result, "balance")

    def test_bank_resolve_partial(self):
        from casino.commands.bank import _resolve_subcommand

        result = _resolve_subcommand("bal")
        self.assertEqual(result, "balance")

    def test_admin_resolve_exact(self):
        from casino.commands.admin import _resolve_subcommand

        result = _resolve_subcommand("watch")
        self.assertEqual(result, "watch")


class TestCommandFunctions(unittest.TestCase):
    """Test command functions with mocks."""

    def test_list_tables_no_client(self):
        with patch("casino.commands.table.lib.get_client", return_value=None):
            from casino.commands.table.lib import list_tables

            args = MagicMock()
            result = list_tables(args)
            self.assertFalse(result)

    def test_list_tables_with_client(self):
        mock_client = MagicMock()
        mock_client.cmd_list_tables = MagicMock()
        mock_client._loop = MagicMock()
        mock_client._loop.run_until_complete = MagicMock()

        with patch("casino.commands.table.lib.get_client", return_value=mock_client):
            from casino.commands.table.lib import list_tables

            args = MagicMock()
            result = list_tables(args)
            mock_client.cmd_list_tables.assert_called_once()
            self.assertTrue(result)

    def test_bet_no_client(self):
        with patch("casino.commands.game.lib.get_client", return_value=None):
            from casino.commands.game.lib import bet

            args = MagicMock()
            result = bet(args)
            self.assertFalse(result)

    def test_hit_no_client(self):
        with patch("casino.commands.game.lib.get_client", return_value=None):
            from casino.commands.game.lib import hit

            args = MagicMock()
            result = hit(args)
            self.assertFalse(result)

    def test_chat_no_client(self):
        with patch("casino.commands.chat.lib.get_client", return_value=None):
            from casino.commands.chat.lib import chat

            args = MagicMock()
            result = chat(args)
            self.assertFalse(result)

    def test_table_chat_not_at_table(self):
        mock_client = MagicMock()
        mock_client.current_table = None

        with patch("casino.commands.chat.lib.get_client", return_value=mock_client):
            from casino.commands.chat.lib import table_chat

            args = MagicMock()
            result = table_chat(args)
            self.assertFalse(result)

    def test_watch_table_no_client(self):
        with patch("casino.commands.admin.lib.get_client", return_value=None):
            from casino.commands.admin.lib import watch_table

            args = MagicMock()
            result = watch_table(args)
            self.assertFalse(result)


class TestMainDispatch(unittest.TestCase):
    """Test main.py parse_module_path function."""

    def test_parse_module_path_with_subcommand(self):
        from casino.main import parse_module_path

        module, subcommand = parse_module_path("table.list")
        self.assertEqual(module, "table")
        self.assertEqual(subcommand, "list")

    def test_parse_module_path_without_subcommand(self):
        from casino.main import parse_module_path

        module, subcommand = parse_module_path("bank")
        self.assertEqual(module, "bank")
        self.assertIsNone(subcommand)

    def test_parse_module_path_connect_disconnect(self):
        from casino.main import parse_module_path

        module, subcommand = parse_module_path("connect.disconnect")
        self.assertEqual(module, "connect")
        self.assertEqual(subcommand, "disconnect")


class TestCasinoClientExtensions(unittest.TestCase):
    """Test CasinoClient has required attributes."""

    def test_last_available_actions_attribute(self):
        from casino.connect import CasinoClient

        args = MagicMock()
        args.casino_host = "localhost"
        args.casino_port = 8765
        client = CasinoClient(args)
        self.assertTrue(hasattr(client, "last_available_actions"))
        self.assertEqual(client.last_available_actions, [])


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestCommandExports))
    suite.addTests(loader.loadTestsFromTestCase(TestSubcommandResolution))
    suite.addTests(loader.loadTestsFromTestCase(TestCommandFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestMainDispatch))
    suite.addTests(loader.loadTestsFromTestCase(TestCasinoClientExtensions))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
