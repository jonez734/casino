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
            create_table,
            list_tables,
            menu,
        )

        self.assertTrue(callable(list_tables))
        self.assertTrue(callable(create_table))
        self.assertTrue(callable(menu))

    def test_game_exports(self):
        from casino.commands.game.lib import (
            bet,
            hit,
            play,
        )

        self.assertTrue(callable(bet))
        self.assertTrue(callable(hit))
        self.assertTrue(callable(play))

    def test_chat_exports(self):
        from casino.commands.chat.lib import chat, table_chat

        self.assertTrue(callable(chat))
        self.assertTrue(callable(table_chat))

    def test_bank_exports(self):
        from casino.commands.bank.lib import (
            bank_balance,
            menu,
        )

        self.assertTrue(callable(menu))
        self.assertTrue(callable(bank_balance))

    def test_admin_exports(self):
        from casino.commands.admin.lib import unwatch_table, watch_table

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
        mock_client.current_table_moniker = None

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

    def test_parse_module_path_auth_disconnect(self):
        from casino.main import parse_module_path

        module, subcommand = parse_module_path("auth.disconnect")
        self.assertEqual(module, "auth")
        self.assertEqual(subcommand, "disconnect")


class TestMainmenuOptions(unittest.TestCase):
    """Test the (key, title, module.subcommand) tuples in casino.main."""

    def test_yahtzee_option_present(self):
        """The Y option must route to yahtzee.play."""
        import ast
        import inspect

        from casino import main as main_module

        src = inspect.getsource(main_module)
        tree = ast.parse(src)
        options_tuple = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "options"
            ):
                options_tuple = ast.literal_eval(node.value)
                break

        self.assertIsNotNone(options_tuple, "options tuple not found in main.py")
        yahtzee = [o for o in options_tuple if o[0] == "Y"]
        self.assertEqual(len(yahtzee), 1)
        self.assertEqual(yahtzee[0][1], "Yahtzee")
        self.assertEqual(yahtzee[0][2], "yahtzee.play")


class TestMainmenuHelpWiring(unittest.TestCase):
    """casino.main.mainmenuhelp() must wire util.heading("main menu")
    so that KEY_HELP redraws the option list with a banner. Each
    invocation of mainmenuhelp must call util.heading exactly once.
    """

    def test_mainmenuhelp_calls_heading_exactly_once(self):
        """Each call to mainmenuhelp must invoke util.heading once."""
        # mainmenuhelp is defined inside main(); we read its source
        # out of main.py and exec it in a controlled namespace.
        import ast
        import inspect
        import textwrap
        from unittest.mock import MagicMock

        from casino import main as main_module

        src = inspect.getsource(main_module.main)
        tree = ast.parse(textwrap.dedent(src))
        mainmenuhelp_node = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "mainmenuhelp"
            ):
                mainmenuhelp_node = node
                break

        self.assertIsNotNone(
            mainmenuhelp_node, "mainmenuhelp() not found inside main()"
        )

        # Rebuild a tiny module that defines `options` and the
        # `mainmenuhelp` function, with `util.heading` and `io.echo`
        # mocked. We capture the rebuilt function in a callable.
        ns: dict = {
            "options": (
                ("B", "Blackjack", "blackjack.play"),
                ("S", "Slots", "slots.play"),
                ("Y", "Yahtzee", "yahtzee.play"),
                ("C", "Connect", "auth"),
                ("Q", "Quit", "quit"),
            ),
        }
        mock_heading = MagicMock()
        ns["util"] = MagicMock()
        ns["util"].heading = mock_heading
        ns["io"] = MagicMock()
        ns["io"].echo = MagicMock()
        # Compile and exec just the mainmenuhelp function.
        module_ast = ast.Module(body=[mainmenuhelp_node], type_ignores=[])
        ast.fix_missing_locations(module_ast)
        exec(compile(module_ast, "<mainmenuhelp>", "exec"), ns)

        mainmenuhelp = ns["mainmenuhelp"]
        mock_heading.reset_mock()
        mainmenuhelp()
        self.assertEqual(mock_heading.call_count, 1)
        self.assertEqual(mock_heading.call_args.args[0], "main menu")

    def test_mainmenuhelp_uses_main_menu_title(self):
        """The heading title must be 'main menu' so F1 shows the right banner."""
        import ast
        import inspect
        import textwrap
        from unittest.mock import MagicMock

        from casino import main as main_module

        src = inspect.getsource(main_module.main)
        tree = ast.parse(textwrap.dedent(src))
        mainmenuhelp_node = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "mainmenuhelp"
            ):
                mainmenuhelp_node = node
                break

        ns: dict = {
            "options": (
                ("B", "Blackjack", "blackjack.play"),
            ),
        }
        ns["util"] = MagicMock()
        ns["io"] = MagicMock()
        module_ast = ast.Module(body=[mainmenuhelp_node], type_ignores=[])
        ast.fix_missing_locations(module_ast)
        exec(compile(module_ast, "<mainmenuhelp>", "exec"), ns)

        ns["mainmenuhelp"]()
        ns["util"].heading.assert_called_once_with("main menu")


class TestCasinoClientExtensions(unittest.TestCase):
    """Test CasinoClient has required attributes."""

    def test_last_available_actions_attribute(self):
        from casino.client import CasinoClient

        args = MagicMock()
        args.bed_host = "localhost"
        args.bed_port = 8765
        args.bed_path = "/"
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
