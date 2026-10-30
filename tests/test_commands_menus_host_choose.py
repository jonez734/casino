"""Stage 8e: the commands/*/lib.py submenus choose through the host seam.

Each submenu reads one answer with ``host.choose`` and normalizes it to uppercase before its
``if cmd == "X"`` chain. Hosted (LO returns lowercase) and standalone (io.inputchoice returns
uppercase) must reach the same branch. These tests drive the real menu functions, with the
sub-actions patched out, and check:
  - the hosted menu receives the menu's letters and default;
  - a lowercase hosted answer runs the branch its uppercase form selects;
  - quit (lowercase 'q') returns without running any action.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

from casino import host


pytestmark = pytest.mark.unit

bj_lib = importlib.import_module("casino.commands.blackjack.lib")
table_lib = importlib.import_module("casino.commands.table.lib")
slots_lib = importlib.import_module("casino.commands.slots.lib")


@pytest.fixture(autouse=True)
def _standalone_after():
    host.unregister_menu()
    yield
    host.unregister_menu()


def _close_coro(coro):
    """Close a coroutine handed to a mocked loop, so it is not left unawaited."""
    if hasattr(coro, "close"):
        coro.close()
    return None


def _loop_safe_client():
    """A mocked client whose loop closes what it is given, so no coroutine is left behind."""
    client = MagicMock()
    client._loop.run_until_complete.side_effect = _close_coro
    return client


def _hosted(answers):
    """Register a hosted menu that returns ``answers`` in turn. Records each call."""
    calls = []
    it = iter(answers)

    def menu(prompt, registry, default="", help=None):
        calls.append({"keys": sorted(registry.keys()), "default": default})
        return next(it)

    host.register_menu(menu)
    return calls


# ---- blackjack: simplest menu, needs no client ---------------------------------------------

def test_blackjack_menu_hosted_lists_p_and_q_with_default_q():
    calls = _hosted(["q"])
    with patch.object(bj_lib.io, "echo"):
        bj_lib.menu(args=None)
    assert calls[0]["keys"] == ["p", "q"]
    assert calls[0]["default"] == "q"


def test_blackjack_menu_hosted_lowercase_p_runs_play():
    _hosted(["p"])
    with patch.object(bj_lib.io, "echo"), patch.object(bj_lib, "play") as play:
        bj_lib.menu(args=None)
    play.assert_called_once()


def test_blackjack_menu_hosted_lowercase_q_does_not_run_play():
    _hosted(["q"])
    with patch.object(bj_lib.io, "echo"), patch.object(bj_lib, "play") as play:
        bj_lib.menu(args=None)
    play.assert_not_called()


def test_blackjack_menu_standalone_uppercase_p_runs_play():
    """Standalone io.inputchoice returns uppercase 'P'. The same branch must run."""
    with patch.object(bj_lib.io, "echo"), \
         patch.object(host.io, "inputchoice", return_value="P"), \
         patch.object(bj_lib, "play") as play:
        bj_lib.menu(args=None)
    play.assert_called_once()


# ---- table: multi-option menu, client needed for the sub-actions ---------------------------

def test_table_menu_hosted_offers_all_letters_and_default_q():
    calls = _hosted(["q"])
    client = _loop_safe_client()
    with patch.object(table_lib.io, "echo"):
        table_lib.menu(args=None, client=client)
    assert calls[0]["keys"] == sorted(["t", "c", "j", "l", "u", "v", "q"])
    assert calls[0]["default"] == "q"


def test_table_menu_hosted_lowercase_v_runs_view_table():
    _hosted(["v", "q"])
    client = _loop_safe_client()
    with patch.object(table_lib.io, "echo"), \
         patch.object(table_lib, "view_table") as view:
        table_lib.menu(args=None, client=client)
    view.assert_called_once()


def test_table_menu_standalone_uppercase_v_runs_view_table():
    answers = iter(["V", "Q"])
    client = _loop_safe_client()
    with patch.object(table_lib.io, "echo"), \
         patch.object(host.io, "inputchoice", side_effect=lambda *a, **k: next(answers)), \
         patch.object(table_lib, "view_table") as view:
        table_lib.menu(args=None, client=client)
    view.assert_called_once()


# ---- slots: the option string is built at runtime -------------------------------------------

def test_slots_menu_hosted_passes_the_visible_letters_as_registry_keys():
    calls = _hosted(["q"])
    client = _loop_safe_client()
    with patch.object(slots_lib, "_require_authenticated_client", return_value=client), \
         patch.object(slots_lib, "_render_help"), \
         patch.object(slots_lib, "_visible_slots_options", return_value=[("s", "pin"), ("q", "uit")]), \
         patch.object(slots_lib.io, "echo"), \
         patch.object(slots_lib.util, "heading"):
        slots_lib.menu(args=None, client=client)
    assert calls[0]["keys"] == ["q", "s"]
    assert calls[0]["default"] == "q"
