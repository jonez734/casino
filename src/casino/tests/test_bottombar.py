#!/usr/bin/env python3
# casino/tests/test_bottombar.py
#
# Tests for the casino bottombar wiring, modeled on the bed.bank tests in
# ``bed/tests/test_bank_tool.py``. The casino bottombar has:
#
# - left side ``"casino (<datestamp> git <githash>)"`` (the
#   ``casino._version``-driven banner that ``casino.main`` puts on the
#   bar);
# - right side three fragments registered through
#   ``bbsengine6.bottombar``:
#
#   * ``_casino_host_fragment`` -- ``"<host>:<port>"`` or ``"direct"``
#     (leftmost on the right side so a notification fragment prepends
#     even further left);
#   * ``_casino_player_fragment`` -- the bound ``player.moniker``;
#   * ``_casino_credits_fragment`` -- ``"N credits"`` (or
#     ``"1 credit"``) for the bound ``player.credits``.
#
# - a once-per-process ``io.screen.init()`` guard via
#   ``_ensure_screen_initialized``;
# - a cleanup echo via ``_clear_bottombar`` that erases the bottom row
#   on ``finally`` so the bar does not leak past menu() exit.

from __future__ import annotations

import argparse
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")


def _import_lib():
    from casino import lib

    return lib


def _make_args(**overrides) -> argparse.Namespace:
    args = argparse.Namespace()
    args.databasename = "test_db"
    args.databasehost = "localhost"
    args.databaseport = 5432
    args.databaseuser = "test_user"
    args.databasepassword = "test_pass"
    args.bed_host = "127.0.0.1"
    args.bed_port = 8765
    args.bed_path = "/"
    args.debug = False
    args.token_file = None
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _make_player(moniker: str = "alice", credits: int = 100):
    p = MagicMock()
    p.moniker = moniker
    p.credits = credits
    return p


@pytest.fixture
def _save_casino_state():
    """Snapshot/restore the module-level globals + fragment registry so
    test bleed never poisons the next run."""
    lib = _import_lib()
    saved = (
        lib._current_args,
        lib._current_player,
        lib._screen_initialized,
    )
    yield lib
    (
        lib._current_args,
        lib._current_player,
        lib._screen_initialized,
    ) = saved


# ---------------------------------------------------------------------
# Fragment isolation


class TestCasinoBottombarFragments:
    def test_player_fragment_renders_moniker(self, _save_casino_state):
        lib = _save_casino_state
        lib._casino_registry.args = _make_args()
        lib._casino_registry.player = _make_player()
        assert lib._casino_player_fragment() == "alice"

    def test_player_fragment_empty_when_no_player(self, _save_casino_state):
        lib = _save_casino_state
        lib._casino_registry.args = _make_args()
        lib._casino_registry.player = None
        assert lib._casino_player_fragment() == ""

    def test_credits_fragment_pluralizes(self, _save_casino_state):
        lib = _save_casino_state
        lib._casino_registry.args = _make_args()
        lib._casino_registry.player = _make_player(credits=100)
        assert lib._casino_credits_fragment() == "100 credits"

    def test_credits_fragment_singular(self, _save_casino_state):
        lib = _save_casino_state
        lib._casino_registry.args = _make_args()
        lib._casino_registry.player = _make_player(credits=1)
        assert lib._casino_credits_fragment() == "a credit"

    def test_credits_fragment_empty_when_no_player(self, _save_casino_state):
        lib = _save_casino_state
        lib._casino_registry.args = _make_args()
        lib._casino_registry.player = None
        assert lib._casino_credits_fragment() == ""

    def test_host_fragment_bed_mode_shows_host_port(
        self, _save_casino_state
    ):
        lib = _save_casino_state
        args = _make_args(bed_host="h", bed_port=9999)
        args._backend = "bed"
        lib._casino_registry.args = args
        lib._casino_registry.player = _make_player()
        assert lib._casino_host_fragment() == "h:9999"

    def test_host_fragment_direct_mode_shows_direct(
        self, _save_casino_state
    ):
        lib = _save_casino_state
        args = _make_args(bed_host="h", bed_port=9999)
        args._backend = "direct"
        lib._casino_registry.args = args
        lib._casino_registry.player = _make_player()
        assert lib._casino_host_fragment() == "direct"

    def test_host_fragment_uses_defaults_when_attrs_missing(
        self, _save_casino_state
    ):
        lib = _save_casino_state
        args = argparse.Namespace()
        lib._casino_registry.args = args
        lib._casino_registry.player = _make_player()
        assert lib._casino_host_fragment() == "127.0.0.1:8765"

    def test_host_fragment_empty_when_args_unbound(
        self, _save_casino_state
    ):
        lib = _save_casino_state
        lib._casino_registry.args = None
        lib._casino_registry.player = _make_player()
        assert lib._casino_host_fragment() == ""


# ---------------------------------------------------------------------
# Register / unregister lifecycle


class TestCasinoFragmentLifecycle:
    def test_register_registers_all_three_fragments(self):
        lib = _import_lib()
        lib._casino_fragments.clear()
        with patch.object(lib.bottombar, "register_bottombar_fragment") as reg:
            lib._register_casino_fragments()
        ids = [c.args[0] for c in reg.call_args_list]
        assert lib._casino_host_fragment in ids
        assert lib._casino_player_fragment in ids
        assert lib._casino_credits_fragment in ids
        assert (
            ids.index(lib._casino_host_fragment)
            < ids.index(lib._casino_player_fragment)
        )
        assert (
            ids.index(lib._casino_player_fragment)
            < ids.index(lib._casino_credits_fragment)
        )

    def test_register_is_idempotent(self):
        lib = _import_lib()
        lib._casino_fragments.clear()
        with patch.object(lib.bottombar, "register_bottombar_fragment") as reg:
            lib._register_casino_fragments()
            lib._register_casino_fragments()
        assert reg.call_count == 3

    def test_unregister_removes_registered_fragments(self):
        lib = _import_lib()
        lib._casino_fragments.clear()
        with patch.object(lib.bottombar, "register_bottombar_fragment"):
            lib._register_casino_fragments()
        with patch.object(lib.bottombar, "unregister_bottombar_fragment") as unreg:
            lib._unregister_casino_fragments()
        ids = [c.args[0] for c in unreg.call_args_list]
        assert lib._casino_host_fragment in ids
        assert lib._casino_player_fragment in ids
        assert lib._casino_credits_fragment in ids
        assert lib._casino_fragments == []

    def test_unregister_tolerates_empty_registry(self):
        lib = _import_lib()
        lib._casino_fragments.clear()
        with patch.object(lib.bottombar, "unregister_bottombar_fragment") as unreg:
            lib._unregister_casino_fragments()
        assert unreg.call_count == 0


# ---------------------------------------------------------------------
# screen.init() once-per-process guard + cleanup echo


class TestCasinoScreenInitGuard:
    def test_ensure_screen_initialized_calls_screen_init_first_time(
        self, _save_casino_state
    ):
        lib = _save_casino_state
        lib._screen_initialized = False
        with patch.object(lib.bbsengine6_screen, "init") as init:
            lib._ensure_screen_initialized()
        init.assert_called_once_with()
        assert lib._screen_initialized is True

    def test_ensure_screen_initialized_skips_when_already_initialized(
        self, _save_casino_state
    ):
        lib = _save_casino_state
        lib._screen_initialized = True
        with patch.object(lib.bbsengine6_screen, "init") as init:
            lib._ensure_screen_initialized()
            lib._ensure_screen_initialized()
        init.assert_not_called()

    def test_setbottombar_triggers_screen_init_on_first_call(
        self, _save_casino_state
    ):
        lib = _save_casino_state
        lib._screen_initialized = False
        with patch.object(lib.bbsengine6_screen, "init") as init, \
             patch.object(lib.bottombar, "setbottombar"):
            lib.setbottombar(_make_args(), "casino banner")
        init.assert_called_once_with()
        assert lib._screen_initialized is True

    def test_setbottombar_does_not_re_init_screen(
        self, _save_casino_state
    ):
        lib = _save_casino_state
        lib._screen_initialized = True
        with patch.object(lib.bbsengine6_screen, "init") as init, \
             patch.object(lib.bottombar, "setbottombar"):
            lib.setbottombar(_make_args(), "casino banner")
            lib.setbottombar(_make_args(), "casino banner")
        init.assert_not_called()

    def test_clear_bottombar_emits_escape_sequence(self):
        lib = _import_lib()
        with patch.object(lib, "bbsengine6_terminal") as terminal, \
             patch.object(lib.io, "echo") as echo:
            terminal.height.return_value = 25
            lib._clear_bottombar()
        echo.assert_called_once()
        arg = echo.call_args.args[0]
        assert "{savecursor}" in arg
        assert "{el}" in arg
        assert "{reset}" in arg
        assert "{restorecursor}" in arg
        assert "{curpos:25,0}" in arg
