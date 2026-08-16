#!/usr/bin/env python3
# casino/tests/test_slots_commands.py
# Tests for the slots commands shim and the module.run() dispatch flow
# that connects casino.main's "S" Slots menu entry to the local game.
#
# Mirrors tests/test_blackjack_commands.py so future contributors find
# the same Test* classes with the same shape across both games.

import argparse
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")


def _make_args(**overrides) -> argparse.Namespace:
    base = {"debug": False}
    base.update(overrides)
    return argparse.Namespace(**base)


class TestCommandsSlotsPackage(unittest.TestCase):
    """The commands.slots shim must exist and expose the expected surface."""

    def test_package_importable(self):
        import casino.commands.slots

        self.assertTrue(hasattr(casino.commands.slots, "SUBCOMMANDS"))
        self.assertTrue(hasattr(casino.commands.slots, "main"))
        self.assertTrue(hasattr(casino.commands.slots, "init"))
        self.assertTrue(hasattr(casino.commands.slots, "access"))
        self.assertTrue(hasattr(casino.commands.slots, "buildargs"))

    def test_subcommands_dict_has_ws_backed_ops(self):
        from casino.commands.slots import SUBCOMMANDS

        for name in ("spin", "paytable", "history", "play"):
            self.assertIn(name, SUBCOMMANDS)
            self.assertTrue(callable(SUBCOMMANDS[name]))

    def test_lib_exports(self):
        from casino.commands.slots import lib

        for name in (
            "menu",
            "play",
            "slot_spin",
            "slot_paytable",
            "slot_history",
            "_check_access",
        ):
            self.assertTrue(callable(getattr(lib, name, None)), f"missing {name}")


class TestCommandsSlotsResolveSubcommand(unittest.TestCase):
    """Subcommand prefix resolution for the slots commands shim."""

    def test_exact_match(self):
        from casino.commands.slots import _resolve_subcommand

        self.assertEqual(_resolve_subcommand("play"), "play")

    def test_partial_match(self):
        from casino.commands.slots import _resolve_subcommand

        self.assertEqual(_resolve_subcommand("pl"), "play")

    def test_empty_returns_none(self):
        from casino.commands.slots import _resolve_subcommand

        self.assertIsNone(_resolve_subcommand(""))

    def test_no_match_returns_none(self):
        from casino.commands.slots import _resolve_subcommand

        self.assertIsNone(_resolve_subcommand("xyz"))


class TestCommandsSlotsMainDispatch(unittest.TestCase):
    """commands.slots.main dispatches subcommands via SUBCOMMANDS."""

    def test_no_subcommand_invokes_menu(self):
        from casino.commands.slots import main

        with patch("casino.commands.slots.lib.menu") as mock_menu:
            result = main(_make_args())
        mock_menu.assert_called_once()
        self.assertTrue(result)

    def test_spin_subcommand_invokes_callback(self):
        from casino.commands.slots import SUBCOMMANDS, main

        mock_cb = MagicMock(return_value=True)
        original = SUBCOMMANDS["spin"]
        SUBCOMMANDS["spin"] = mock_cb
        try:
            result = main(_make_args(), subcommand="spin")
        finally:
            SUBCOMMANDS["spin"] = original
        mock_cb.assert_called_once()
        self.assertTrue(result)

    def test_play_subcommand_still_routes_to_spin(self):
        """The legacy ``play`` subcommand is kept as an alias for spin
        so existing callers (e.g. ``slots.play``) keep working."""
        from casino.commands.slots import SUBCOMMANDS, main

        mock_cb = MagicMock(return_value=True)
        original_play = SUBCOMMANDS["play"]
        SUBCOMMANDS["play"] = mock_cb
        try:
            result = main(_make_args(), subcommand="play")
        finally:
            SUBCOMMANDS["play"] = original_play
        mock_cb.assert_called_once()
        self.assertTrue(result)

    def test_ambiguous_or_unknown_subcommand_falls_back_to_menu(self):
        from casino.commands.slots import main

        with patch("casino.commands.slots.lib.menu") as mock_menu:
            result = main(_make_args(), subcommand="nonexistent")
        mock_menu.assert_called_once()
        self.assertTrue(result)


class TestSlotSpinUsesClient(unittest.TestCase):
    """commands/slots/lib.py:slot_spin() must go through the WS client
    so the bearer token is auto-injected on every wire call. The
    access gate uses ``bbsengine6.casino.access`` so the local CLI
    agrees with the server's per-op authorization.
    """

    def _authed_client(self) -> MagicMock:
        client = MagicMock()
        client.authenticated = True
        client.moniker = "alice"
        client.current_table_moniker = "t1"
        client.cmd_slot_spin = MagicMock()
        client.cmd_slot_paytable = MagicMock()
        client.cmd_slot_history = MagicMock()
        client._loop = MagicMock()
        return client

    def test_slot_spin_requires_a_connected_client(self):
        from casino.commands.slots import lib

        with patch("casino.commands.slots.lib.get_client", return_value=None):
            result = lib.slot_spin(_make_args())
        self.assertFalse(result)

    def test_slot_spin_rejects_unauthenticated_client(self):
        """A client in the registry that hasn't actually finished
        authenticating must not be able to spin."""
        from casino.commands.slots import lib

        client = MagicMock()
        client.authenticated = False
        client.moniker = "alice"
        client.cmd_slot_spin = MagicMock()

        with patch("casino.commands.slots.lib.get_client", return_value=client):
            result = lib.slot_spin(_make_args())
        self.assertFalse(result)
        client.cmd_slot_spin.assert_not_called()

    def test_slot_spin_rejects_client_with_empty_moniker(self):
        from casino.commands.slots import lib

        client = MagicMock()
        client.authenticated = True
        client.moniker = ""
        client.cmd_slot_spin = MagicMock()

        with patch("casino.commands.slots.lib.get_client", return_value=client):
            result = lib.slot_spin(_make_args())
        self.assertFalse(result)
        client.cmd_slot_spin.assert_not_called()

    def test_slot_spin_gates_through_casino_access(self):
        from casino.commands.slots import lib

        client = self._authed_client()

        with patch(
            "casino.commands.slots.lib.get_client", return_value=client
        ), patch(
            "casino.commands.slots.lib._casino_access", return_value=True
        ) as mock_access:
            result = lib.slot_spin(_make_args(_session_moniker="alice"))

        self.assertTrue(result)
        mock_access.assert_called_once()
        op_arg = mock_access.call_args.args[1]
        self.assertEqual(op_arg, "slot_spin")
        client.cmd_slot_spin.assert_called_once()

    def test_slot_spin_denied_when_access_denies(self):
        from casino.commands.slots import lib

        client = self._authed_client()

        with patch(
            "casino.commands.slots.lib.get_client", return_value=client
        ), patch(
            "casino.commands.slots.lib._casino_access", return_value=False
        ):
            result = lib.slot_spin(_make_args(_session_moniker="alice"))

        self.assertFalse(result)
        client.cmd_slot_spin.assert_not_called()

    def test_slot_spin_denied_without_session_moniker(self):
        from casino.commands.slots import lib

        client = self._authed_client()

        result = lib.slot_spin(_make_args())  # no _session_moniker
        self.assertFalse(result)
        client.cmd_slot_spin.assert_not_called()

    def test_play_aliases_slot_spin(self):
        """``lib.play`` must delegate to ``slot_spin`` so the legacy
        ``slots.play`` subcommand path keeps working."""
        from casino.commands.slots import lib

        client = self._authed_client()

        with patch(
            "casino.commands.slots.lib.get_client", return_value=client
        ), patch(
            "casino.commands.slots.lib._casino_access", return_value=True
        ):
            result = lib.play(_make_args(_session_moniker="alice"))
        self.assertTrue(result)
        client.cmd_slot_spin.assert_called_once()


class TestSlotPaytableUsesClient(unittest.TestCase):
    """slot_paytable must mirror slot_spin's auth gate."""

    def _authed_client(self) -> MagicMock:
        client = MagicMock()
        client.authenticated = True
        client.moniker = "alice"
        client.current_table_moniker = "t1"
        client.cmd_slot_paytable = MagicMock()
        client._loop = MagicMock()
        return client

    def test_slot_paytable_requires_a_connected_client(self):
        from casino.commands.slots import lib

        with patch("casino.commands.slots.lib.get_client", return_value=None):
            self.assertFalse(lib.slot_paytable(_make_args()))

    def test_slot_paytable_rejects_unauthenticated_client(self):
        from casino.commands.slots import lib

        client = MagicMock()
        client.authenticated = False
        client.moniker = "alice"
        client.cmd_slot_paytable = MagicMock()

        with patch("casino.commands.slots.lib.get_client", return_value=client):
            self.assertFalse(lib.slot_paytable(_make_args()))
        client.cmd_slot_paytable.assert_not_called()

    def test_slot_paytable_gates_through_casino_access(self):
        from casino.commands.slots import lib

        client = self._authed_client()
        with patch(
            "casino.commands.slots.lib.get_client", return_value=client
        ), patch(
            "casino.commands.slots.lib._casino_access", return_value=True
        ) as mock_access:
            self.assertTrue(
                lib.slot_paytable(_make_args(_session_moniker="alice"))
            )
        mock_access.assert_called_once()
        self.assertEqual(mock_access.call_args.args[1], "slot_paytable")
        client.cmd_slot_paytable.assert_called_once()


class TestSlotHistoryUsesClient(unittest.TestCase):
    """slot_history must mirror slot_spin's auth gate."""

    def _authed_client(self) -> MagicMock:
        client = MagicMock()
        client.authenticated = True
        client.moniker = "alice"
        client.current_table_moniker = "t1"
        client.cmd_slot_history = MagicMock()
        client._loop = MagicMock()
        return client

    def test_slot_history_requires_a_connected_client(self):
        from casino.commands.slots import lib

        with patch("casino.commands.slots.lib.get_client", return_value=None):
            self.assertFalse(lib.slot_history(_make_args()))

    def test_slot_history_rejects_unauthenticated_client(self):
        from casino.commands.slots import lib

        client = MagicMock()
        client.authenticated = False
        client.moniker = "alice"
        client.cmd_slot_history = MagicMock()

        with patch("casino.commands.slots.lib.get_client", return_value=client):
            self.assertFalse(lib.slot_history(_make_args()))
        client.cmd_slot_history.assert_not_called()

    def test_slot_history_gates_through_casino_access(self):
        from casino.commands.slots import lib

        client = self._authed_client()
        with patch(
            "casino.commands.slots.lib.get_client", return_value=client
        ), patch(
            "casino.commands.slots.lib._casino_access", return_value=True
        ) as mock_access:
            self.assertTrue(
                lib.slot_history(_make_args(_session_moniker="alice"))
            )
        mock_access.assert_called_once()
        self.assertEqual(mock_access.call_args.args[1], "slot_history")
        client.cmd_slot_history.assert_called_once()


class TestSlotsMenuRefusesUnauthenticated(unittest.TestCase):
    """The slots submenu must refuse to open without an authenticated
    client. The gate fires before the heading / help / prompt so a
    user who hasn't connected cannot even see the [S]pin option.
    """

    def test_menu_refuses_when_no_client(self):
        from casino.commands.slots import lib

        with patch("casino.commands.slots.lib.get_client", return_value=None), \
             patch("bbsengine6.io.inputchoice") as mock_ic, \
             patch("bbsengine6.io.echo"):
            result = lib.menu(_make_args())
        mock_ic.assert_not_called()
        self.assertTrue(result)

    def test_menu_refuses_when_client_not_authenticated(self):
        from casino.commands.slots import lib

        client = MagicMock()
        client.authenticated = False
        client.moniker = ""

        with patch("casino.commands.slots.lib.get_client", return_value=client), \
             patch("bbsengine6.io.inputchoice") as mock_ic, \
             patch("bbsengine6.io.echo"):
            result = lib.menu(_make_args())
        mock_ic.assert_not_called()
        self.assertTrue(result)

    def test_menu_opens_for_authenticated_client(self):
        from casino.commands.slots import lib

        client = MagicMock()
        client.authenticated = True
        client.moniker = "alice"
        client.current_table_moniker = "t1"
        client.cmd_slot_spin = MagicMock()
        client._loop = MagicMock()

        with patch("casino.commands.slots.lib.get_client", return_value=client), \
             patch("bbsengine6.io.inputchoice", return_value="q") as mock_ic:
            result = lib.menu(_make_args(_session_moniker="alice"))
        mock_ic.assert_called_once()
        self.assertTrue(result)


class TestSlotsPackageMainUsesModuleRun(unittest.TestCase):
    """casino.slots.main() must route through module.run() so callers like
    casino.slots.__main__ get the standard machinery (registration,
    buildargs, signature checks)."""

    def test_init_main_delegates_to_module_run(self):
        import casino.slots

        sentinel = object()
        with patch("bbsengine6.module.run", return_value=sentinel) as mock_run:
            result = casino.slots.main(_make_args(), extra_kw="value")

        self.assertIs(result, sentinel)
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[1], "game")
        self.assertEqual(kwargs.get("package"), "casino.slots")
        self.assertEqual(kwargs.get("extra_kw"), "value")


class TestSlotsGameRegistersItself(unittest.TestCase):
    """casino.slots.game.init() must call register_module() so bbsengine6
    recognizes the inner game module."""

    def test_game_init_calls_register_module(self):
        from casino.slots import game

        with patch("casino.slots.game.register_module") as mock_reg:
            result = game.init(_make_args())

        self.assertTrue(result)
        mock_reg.assert_called_once()
        kwargs = mock_reg.call_args.kwargs
        self.assertEqual(kwargs.get("name"), "casino.slots.game")
        self.assertEqual(kwargs.get("module_path"), "casino.slots.game")


class TestModuleCheckPasses(unittest.TestCase):
    """bbsengine6.module.check() must accept the new slots modules."""

    def test_commands_slots_passes(self):
        from bbsengine6 import module

        self.assertTrue(
            module.check(_make_args(), "slots", package="casino.commands")
        )

    def test_slots_package_passes(self):
        from bbsengine6 import module

        self.assertTrue(module.check(_make_args(), "casino.slots"))

    def test_slots_game_passes(self):
        from bbsengine6 import module

        self.assertTrue(
            module.check(_make_args(), "game", package="casino.slots")
        )


class TestSlotsMenuHelpWiring(unittest.TestCase):
    """commands/slots/lib.py:menu() must wire help= so KEY_HELP redraws the
    option list. The help callback must call util.heading() exactly once
    per display of help (one F1 press -> one heading). The menu gate
    requires an authenticated client, so the help-wiring tests inject
    one before invoking menu."""

    @staticmethod
    def _authed_client():
        client = MagicMock()
        client.authenticated = True
        client.moniker = "alice"
        client.current_table_moniker = "t1"
        client.cmd_slot_spin = MagicMock()
        client._loop = MagicMock()
        return client

    def test_menu_passes_help_to_inputchoice(self):
        from casino.commands.slots import lib

        client = self._authed_client()
        with patch(
            "casino.commands.slots.lib.get_client", return_value=client
        ), patch(
            "bbsengine6.io.inputchoice", return_value="q"
        ) as mock_ic:
            lib.menu(_make_args(_session_moniker="alice"))

        mock_ic.assert_called_once()
        kwargs = mock_ic.call_args.kwargs
        self.assertIn("help", kwargs)
        self.assertTrue(callable(kwargs["help"]))

    def test_help_callback_calls_heading_exactly_once(self):
        """Simulate one F1 press: util.heading() must be called exactly once."""
        from casino.commands.slots import lib

        client = self._authed_client()
        with patch(
            "casino.commands.slots.lib.get_client", return_value=client
        ), patch(
            "bbsengine6.io.inputchoice"
        ) as mock_ic, patch(
            "casino.commands.slots.lib.util.heading"
        ) as mock_heading:
            lib.menu(_make_args(_session_moniker="alice"))
            mock_heading.reset_mock()
            mock_ic.call_args.kwargs["help"]()
        self.assertEqual(mock_heading.call_count, 1)

    def test_help_callback_uses_slots_heading(self):
        """The heading title must be 'Slots' so F1 shows the right banner."""
        from casino.commands.slots import lib

        client = self._authed_client()
        with patch(
            "casino.commands.slots.lib.get_client", return_value=client
        ), patch(
            "bbsengine6.io.inputchoice"
        ) as mock_ic, patch(
            "casino.commands.slots.lib.util.heading"
        ) as mock_heading:
            lib.menu(_make_args(_session_moniker="alice"))
            mock_heading.reset_mock()
            mock_ic.call_args.kwargs["help"]()
        self.assertEqual(mock_heading.call_args.args[0], "Slots")


class TestSlotsPlayHelpWiring(unittest.TestCase):
    """casino/slots/play.py must wire help= on every interactive prompt
    and call util.heading() exactly once per help redraw."""

    def test_bet_help_calls_heading_exactly_once(self):
        from casino.slots import play

        with patch("casino.slots.play.util.heading") as mock_heading:
            play._render_bet_help()
        self.assertEqual(mock_heading.call_count, 1)
        self.assertEqual(mock_heading.call_args.args[0], "play slots")

    def test_again_help_calls_heading_exactly_once(self):
        from casino.slots import play

        with patch("casino.slots.play.util.heading") as mock_heading:
            play._render_again_help()
        self.assertEqual(mock_heading.call_count, 1)
        self.assertEqual(mock_heading.call_args.args[0], "play slots")


class TestEndToEndDispatch(unittest.TestCase):
    """The full path: casino.commands.slots.main (subcommand='spin')
    -> commands/slots/lib.py:slot_spin() -> client.cmd_slot_spin() ->
    CasinoClient.send (which auto-injects the bearer token).
    """

    def test_spin_subcommand_resolves_ws_client_dispatch(self):
        from casino.commands.slots import SUBCOMMANDS

        self.assertIs(SUBCOMMANDS["spin"].__name__, "slot_spin")
        self.assertTrue(callable(SUBCOMMANDS["spin"]))


class TestMainmenuHookup(unittest.TestCase):
    """The main menu entry ('S', 'Slots', 'slots') must parse cleanly
    and resolve to a callable subcommand. ``slots`` (no subcommand)
    drops into the WS-backed submenu in ``commands/slots/lib.py:menu``."""

    def test_mainmenu_path_loads(self):
        from casino.commands import slots

        self.assertTrue(hasattr(slots, "main"))
        self.assertTrue(callable(slots.main))

    def test_parse_module_path_yields_slots(self):
        from casino.main import parse_module_path

        module, subcommand = parse_module_path("slots")
        self.assertEqual(module, "slots")
        self.assertIsNone(subcommand)


if __name__ == "__main__":
    unittest.main()
