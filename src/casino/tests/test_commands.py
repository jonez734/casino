#!/usr/bin/env python3
# casino/tests/test_commands.py
# Tests for casino commands subpackage

import sys
import unittest
from types import SimpleNamespace
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

        def _run_until_complete(coro):
            # The table handlers pass ``asyncio.sleep(0.1)`` to the
            # loop to give the wire send a chance to flush; under a
            # mock loop we must drive the coroutine ourselves so it
            # isn't garbage-collected unawaited (which would surface
            # as a pytest ``PytestUnraisableExceptionWarning`` and
            # fail the suite).
            try:
                coro.close()
            except Exception:
                pass
            return None

        mock_client._loop.run_until_complete = MagicMock(side_effect=_run_until_complete)

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

    def _extract_options(self):
        """Walk ``casino.main`` source and extract ``MenuOption`` calls
        from the ``options = (...)`` assignment.

        Returns a list of ``(letter, label, module_path)`` tuples in
        declaration order. Mirrors the public surface that the old
        tuple-of-tuples spec exposed to tests.
        """
        import ast
        import inspect

        from casino import main as main_module

        src = inspect.getsource(main_module)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "options"
            ):
                # ``node.value`` is a Tuple whose elements are
                # ``MenuOption(...)`` ``Call`` nodes (positional
                # args: letter, label, module_path).
                out = []
                for elt in node.value.elts:
                    if not isinstance(elt, ast.Call):
                        continue
                    if not (
                        isinstance(elt.func, ast.Name)
                        and elt.func.id == "MenuOption"
                    ):
                        continue
                    letter = elt.args[0].value
                    label = elt.args[1].value
                    module_path = elt.args[2].value
                    out.append((letter, label, module_path))
                return out
        return None

    def test_yahtzee_option_present(self):
        """The Y option must route to yahtzee.play."""
        options = self._extract_options()
        self.assertIsNotNone(options, "options tuple not found in main.py")
        yahtzee = [o for o in options if o[0] == "y"]
        self.assertEqual(len(yahtzee), 1)
        self.assertEqual(yahtzee[0][1], "Yahtzee")
        self.assertEqual(yahtzee[0][2], "yahtzee.play")


class TestMainmenuHelpWiring(unittest.TestCase):
    """casino.main.mainmenuhelp() must wire util.heading("casino main menu")
    so that KEY_HELP redraws the option list with a banner. Each
    invocation of mainmenuhelp must call util.heading exactly once.
    """

    def _exec_mainmenuhelp_in_namespace(self):
        """Extract ``mainmenuhelp`` from ``casino.main`` and exec it
        in a controlled namespace with the closures it references
        (``_menu_state``, ``currentplayer``, ``remote_client``,
        ``visible_options``, ``options``) stubbed out.
        """
        import ast
        import inspect
        from unittest.mock import MagicMock

        # Import the *module* (not the ``main`` function from
        # ``casino/__init__.py``) so we can read the source of the
        # door-mode ``mainmenuhelp`` nested inside ``casino.main:main``.
        import casino.main as main_module

        src = inspect.getsource(main_module)
        tree = ast.parse(src)
        # Find ``def main(...)`` at module level, then walk into its
        # body for the nested ``def mainmenuhelp(...)``.
        main_node = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                main_node = node
                break
        self.assertIsNotNone(main_node, "def main() not found in casino.main")

        mainmenuhelp_node = None
        for node in ast.walk(main_node):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "mainmenuhelp"
            ):
                mainmenuhelp_node = node
                break

        self.assertIsNotNone(
            mainmenuhelp_node, "mainmenuhelp() not found inside main()"
        )

        # Stub closures. ``_menu_state`` returns ``currentplayer``
        # with its ``connected`` attribute set from the second arg.
        ns: dict = {}
        currentplayer_mock = MagicMock()
        ns["currentplayer"] = currentplayer_mock
        ns["remote_client"] = None

        def fake_menu_state(player, connected):
            player.connected = connected
            return player

        ns["_menu_state"] = fake_menu_state

        def fake_visible_options(opts, state):
            return list(opts)

        ns["visible_options"] = fake_visible_options
        # Provide MenuOption-shaped stubs. ``letter``/``label`` are
        # the attributes ``mainmenuhelp`` reads; we don't need full
        # gate semantics for the heading assertion.
        class _OptStub:
            def __init__(self, letter, label):
                self.letter = letter
                self.label = label

        ns["options"] = (
            _OptStub("b", "Blackjack"),
            _OptStub("y", "Yahtzee"),
            _OptStub("c", "Connect"),
            _OptStub("q", "Quit"),
        )
        mock_heading = MagicMock()
        ns["util"] = MagicMock()
        ns["util"].heading = mock_heading
        ns["io"] = MagicMock()
        ns["io"].echo = MagicMock()

        module_ast = ast.Module(body=[mainmenuhelp_node], type_ignores=[])
        ast.fix_missing_locations(module_ast)
        exec(compile(module_ast, "<mainmenuhelp>", "exec"), ns)
        return ns, mock_heading

    def test_mainmenuhelp_calls_heading_exactly_once(self):
        """Each call to mainmenuhelp must invoke util.heading once."""
        ns, mock_heading = self._exec_mainmenuhelp_in_namespace()
        ns["mainmenuhelp"]()
        self.assertEqual(mock_heading.call_count, 1)
        self.assertEqual(mock_heading.call_args.args[0], "casino main menu")

    def test_mainmenuhelp_uses_main_menu_title(self):
        """The heading title must be 'casino main menu' so F1 shows the right banner."""
        ns, _mock_heading = self._exec_mainmenuhelp_in_namespace()
        ns["mainmenuhelp"]()
        ns["util"].heading.assert_called_once_with("casino main menu")


class TestMainmenuDuplicateP(unittest.TestCase):
    """Pin the contract that the two ``P`` entries in ``casino.main``'s
    ``options`` -- ``Play`` (``requires_seated=True``) and the Poker
    launcher (``hide_if_seated_type={\"poker\"}``) -- never both surface
    when the visibility filter can disambiguate. Historically both
    letters appeared in every menu draw, so this pins the fix.

    Contract:
      * Not seated at any table: only the Poker launcher is visible.
      * Seated at a poker table: only the Play action is visible.

    Seating at blackjack or yahtzee intentionally still shows both
    ``P`` entries because the player may want to start a poker hand
    without leaving their seat; that is the existing spec and is not
    part of this contract.
    """

    @staticmethod
    def _kwarg_value(node):
        """Convert a kwarg AST node to a Python value. Handles
        literal constants and ``frozenset({...})`` calls; anything
        else raises so a future spec change is caught loudly.
        """
        import ast

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "frozenset"
            and len(node.args) == 1
        ):
            return frozenset(ast.literal_eval(node.args[0]))
        return ast.literal_eval(node)

    def _options(self):
        """Walk ``casino.main`` source and return the ``options``
        tuple as a list of ``MenuOption`` instances with kwargs.
        """
        import ast
        import importlib
        import inspect

        # Import the submodule explicitly: ``from casino import main``
        # returns the ``main`` function re-exported from
        # ``casino/__init__.py`` unless ``casino.main`` is already
        # cached in ``sys.modules``. Importing the submodule first
        # keeps this test order-independent.
        main_module = importlib.import_module("casino.main")
        from casino.menu_lib import MenuOption

        src = inspect.getsource(main_module)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "options"
            ):
                out = []
                for elt in node.value.elts:
                    if not (
                        isinstance(elt, ast.Call)
                        and isinstance(elt.func, ast.Name)
                        and elt.func.id == "MenuOption"
                    ):
                        continue
                    args = [ast.literal_eval(a) for a in elt.args]
                    kwargs = {
                        kw.arg: self._kwarg_value(kw.value) for kw in elt.keywords
                    }
                    out.append(MenuOption(*args, **kwargs))
                return out
        return None

    def _p_labels(self, options, state):
        from casino.menu_lib import visible_options

        return [o.label for o in visible_options(options, state) if o.letter == "p"]

    def test_unseated_shows_only_poker_launcher(self):
        options = self._options()
        self.assertIsNotNone(options, "options tuple not found in main.py")
        state = SimpleNamespace(
            current_table_moniker=None,
            current_table_game_type=None,
            connected=False,
        )
        labels = self._p_labels(options, state)
        self.assertEqual(
            labels,
            ["Poker"],
            f"expected only Poker launcher visible when unseated, got {labels}",
        )

    def test_seated_at_poker_hides_poker_launcher(self):
        options = self._options()
        self.assertIsNotNone(options)
        state = SimpleNamespace(
            current_table_moniker="poker-1",
            current_table_game_type="poker",
            connected=True,
        )
        labels = self._p_labels(options, state)
        self.assertEqual(
            labels,
            ["Play"],
            f"expected only Play visible when seated at poker, got {labels}",
        )


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


class TestSlotsMenuVisibility(unittest.TestCase):
    """Slots submenu must hide [S]pin / [P]aytable unless the player
    is seated at a slots table. [H]istory is player-scope so it stays
    visible from any state; [Q]uit is unconditional.
    """

    def test_no_table_shows_only_history_and_quit(self):
        from casino.commands.slots.lib import _visible_slots_options

        visible = "".join(t[0].upper() for t in _visible_slots_options(None))
        self.assertIn("H", visible)
        self.assertIn("Q", visible)
        self.assertNotIn("S", visible)
        self.assertNotIn("P", visible)

    def test_non_slots_table_still_hides_spin_and_paytable(self):
        from casino.commands.slots.lib import _visible_slots_options

        for gt in ("blackjack", "poker", "tictactoe", "yahtzee"):
            client = SimpleNamespace(current_table_moniker="tbl", current_table_game_type=gt)
            visible = "".join(t[0].upper() for t in _visible_slots_options(client))
            self.assertIn("H", visible)
            self.assertIn("Q", visible)
            self.assertNotIn("S", visible, f"S should be hidden at {gt} table")
            self.assertNotIn("P", visible, f"P should be hidden at {gt} table")

    def test_slots_table_shows_full_submenu(self):
        from casino.commands.slots.lib import _visible_slots_options

        client = SimpleNamespace(current_table_moniker="tbl", current_table_game_type="slots")
        visible = "".join(t[0].upper() for t in _visible_slots_options(client))
        self.assertEqual(visible, "SPHQ")

    def test_post_join_window_keeps_spin_paytable_hidden(self):
        from casino.commands.slots.lib import _visible_slots_options

        client = SimpleNamespace(current_table_moniker="tbl", current_table_game_type=None)
        visible = "".join(t[0].upper() for t in _visible_slots_options(client))
        self.assertIn("H", visible)
        self.assertIn("Q", visible)
        self.assertNotIn("S", visible)
        self.assertNotIn("P", visible)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestCommandExports))
    suite.addTests(loader.loadTestsFromTestCase(TestSubcommandResolution))
    suite.addTests(loader.loadTestsFromTestCase(TestCommandFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestMainDispatch))
    suite.addTests(loader.loadTestsFromTestCase(TestCasinoClientExtensions))
    suite.addTests(loader.loadTestsFromTestCase(TestSlotsMenuVisibility))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
