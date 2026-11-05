"""Slots and tictactoe menus on menu_next: key mode, --rounds, the main-menu slots entry, and the
message-type contracts the server registration reads.
"""

import argparse
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _authed_client(**extra):
    client = MagicMock()
    client.authenticated = True
    client.moniker = "alice"
    client.current_table_moniker = "t1"
    client.current_table_game_type = "slots"
    client._loop = MagicMock()
    for k, v in extra.items():
        setattr(client, k, v)
    return client


class TestMessageTypeContracts(unittest.TestCase):
    """Each game's declared wire types are the ones the server registers."""

    def test_slot_types_are_declared(self):
        from casino.api.handler import SlotServiceHandler

        self.assertEqual(
            set(SlotServiceHandler.SLOT_MSG_TYPES),
            {"slot_spin", "slot_paytable", "slot_history", "slot_table_history"},
        )

    def test_tictactoe_types_are_declared(self):
        from casino.tictactoe.api_handler import TictactoeServiceHandler as H

        self.assertEqual(
            set(H.TICTACTOE_MSG_TYPES),
            {"tictactoe_quick_play", "tictactoe_move", "tictactoe_resign", "tictactoe_join"},
        )


class TestTictactoeTableVerbs(unittest.TestCase):
    """move and resign act on the seated table; quickplay and join stay tictactoe subcommands."""

    def test_move_and_resign_are_tictactoe_table_verbs(self):
        from casino.commands.table import play

        self.assertIn("move", play.PLAY_VERBS["tictactoe"])
        self.assertIn("resign", play.PLAY_VERBS["tictactoe"])

    def test_quickplay_and_join_are_not_table_verbs(self):
        from casino.commands.table import play

        self.assertNotIn("quickplay", play.PLAY_VERBS["tictactoe"])
        self.assertNotIn("join", play.PLAY_VERBS["tictactoe"])

    def test_move_is_refused_at_a_blackjack_table(self):
        from casino.commands.table import play

        result = play.resolve("move", seated=True, game_type="blackjack")
        self.assertIsInstance(result, play.Refusal)

    def test_move_routes_at_a_tictactoe_table(self):
        from casino.commands.table import play

        self.assertEqual(play.resolve("move", seated=True, game_type="tictactoe"), "tictactoe")


class TestRoundsFlag(unittest.TestCase):
    def test_slots_parses_rounds(self):
        from casino.commands.slots import buildargs

        self.assertEqual(buildargs(None).parse_args(["--rounds=3"]).rounds, 3)

    def test_tictactoe_rounds_defaults_to_none(self):
        from casino.commands.tictactoe import buildargs

        self.assertIsNone(buildargs(None).parse_args([]).rounds)

    def test_rounds_refuses_zero_and_non_numbers(self):
        from casino.commands.slots import buildargs

        for bad in ("--rounds=0", "--rounds=-2", "--rounds=x"):
            with self.subTest(bad=bad), patch("sys.stderr"):
                with self.assertRaises(SystemExit):
                    buildargs(None).parse_args([bad])


class TestSlotsSubmenu(unittest.TestCase):
    def _run_menu(self, keys, rounds=None):
        from casino.commands.slots import lib

        client = _authed_client()
        reads = iter(keys)
        reader = MagicMock(side_effect=lambda *a, **k: next(reads))
        with patch("casino.commands.slots.lib.get_client", return_value=client), \
             patch("casino.commands.slots.lib.host.choose", reader), \
             patch("casino.commands.slots.lib.slot_history") as history, \
             patch("casino.commands.slots.lib.slot_paytable") as paytable, \
             patch("casino.commands.slots.lib.util.heading"), \
             patch("casino.commands.slots.lib._render_help"):
            kwargs = {"rounds": rounds} if rounds is not None else {}
            lib.menu(argparse.Namespace(_session_moniker="alice"), client=client, **kwargs)
        return reader, history, paytable

    def test_one_shot_by_default(self):
        reader, history, _ = self._run_menu(["H", "H", "H"])
        self.assertEqual(reader.call_count, 1)
        history.assert_called_once()

    def test_rounds_runs_up_to_n_actions(self):
        reader, history, _ = self._run_menu(["H", "H", "H", "H"], rounds=3)
        self.assertEqual(reader.call_count, 3)
        self.assertEqual(history.call_count, 3)

    def test_x_exits_early_under_rounds(self):
        reader, history, _ = self._run_menu(["H", "X", "H", "H"], rounds=5)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(history.call_count, 1)

    def test_q_alias_exits(self):
        reader, history, _ = self._run_menu(["Q"], rounds=4)
        self.assertEqual(reader.call_count, 1)
        history.assert_not_called()

    def test_slots_hidden_unless_connected(self):
        from bbsengine6.menu_next import visible_options
        from casino.client import menu

        def letters(c):
            return [o.letter for o in visible_options(menu._OPTIONS_SPEC, c, check=menu._checker(c))]

        off = SimpleNamespace(connected=False, authenticated=False,
                              current_table_moniker=None, current_table_game_type=None)
        on = SimpleNamespace(connected=True, authenticated=True,
                             current_table_moniker=None, current_table_game_type=None)
        self.assertNotIn("slots", letters(off))
        self.assertIn("slots", letters(on))


class TestTictactoeSubmenu(unittest.TestCase):
    def _run_menu(self, keys, rounds=None):
        from casino.commands.tictactoe import lib

        client = _authed_client(current_table_game_type="tictactoe")
        reads = iter(keys)
        reader = MagicMock(side_effect=lambda *a, **k: next(reads))
        with patch("casino.commands.tictactoe.lib.host.choose", reader), \
             patch("casino.commands.tictactoe.lib.quickplay") as quick, \
             patch("casino.commands.tictactoe.lib.join") as join:
            kwargs = {"rounds": rounds} if rounds is not None else {}
            lib.menu(argparse.Namespace(), client=client, **kwargs)
        return reader, quick, join

    def test_one_shot_by_default(self):
        reader, quick, _ = self._run_menu(["U", "U"])
        self.assertEqual(reader.call_count, 1)
        quick.assert_called_once()

    def test_rounds_loops_and_x_exits(self):
        reader, quick, join = self._run_menu(["U", "J", "X", "U"], rounds=4)
        self.assertEqual(reader.call_count, 3)
        quick.assert_called_once()
        join.assert_called_once()

    def test_q_alias_is_the_exit(self):
        reader, quick, _ = self._run_menu(["Q"], rounds=3)
        self.assertEqual(reader.call_count, 1)
        quick.assert_not_called()


class TestTopLevelNames(unittest.TestCase):
    def test_clash_check_passes_with_slots(self):
        from casino.client.menu import _OPTIONS_SPEC, _check_top_level_names

        _check_top_level_names(_OPTIONS_SPEC)

    def test_slots_option_is_present_beside_bank(self):
        from casino.client.menu import _OPTIONS_SPEC

        letters = [o.letter for o in _OPTIONS_SPEC]
        self.assertEqual(letters.index("slots"), letters.index("bank") + 1)
