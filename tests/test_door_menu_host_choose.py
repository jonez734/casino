"""Stage 8c: the door-mode main menu chooses through the host seam.

Drives the real ``casino.main`` loop with its database, session, bottombar, and player
stubbed, and a scripted menu choice. Covers:
  - a hosted choice (LO returns the key as stored, lowercase) dispatches the option;
  - a standalone choice (io.inputchoice returns uppercase) dispatches the same option. Before
    8c this case never matched, because the loop compared lowercase option letters to an
    uppercase answer;
  - quit works from either mode, in either case.
"""

from argparse import Namespace
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

import importlib

from casino import host

# ``casino.main`` the attribute is the function; the module is needed for patching.
door = importlib.import_module("casino.main")


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _standalone_after():
    host.unregister_menu()
    yield
    host.unregister_menu()


def _args():
    return Namespace(debug=False, databasename="zoid6", databasehost="h", databaseport=5432,
                     databaseuser="u", databasepassword=None)


class _Pool:
    def __enter__(self):
        return object()

    def __exit__(self, *exc):
        return False


def _player():
    p = MagicMock()
    p.moniker = "alice"
    p.connected = False
    p.current_table_moniker = None
    return p


def _run_door(answer_fn, *, menu_fn=None):
    """Run one pass of the door loop. ``answer_fn`` is what the choice returns.

    ``menu_fn`` (hosted) or the standalone ``io.inputchoice`` both receive the same prompt.
    Returns the menu-dispatched modules: every ``lib.runmodule`` call except the one-time
    ``startup`` step, which runs before the first menu choice.
    """
    dispatched = []

    def runmodule(args, module, package=None, **kw):
        dispatched.append(module)
        return True

    # One choice, then the loop is told to quit on the next iteration by the answer itself.
    with ExitStack() as stack:
        stack.enter_context(patch.object(door.database, "getpool", return_value=_Pool()))
        stack.enter_context(patch.object(door.session, "start", return_value=True))
        stack.enter_context(patch.object(door.lib, "setbottombar"))
        stack.enter_context(patch.object(door.lib, "_unregister_casino_fragments"))
        stack.enter_context(patch.object(door.lib, "_clear_bottombar"))
        stack.enter_context(patch.object(door.member, "getcurrentmoniker", return_value="alice"))
        stack.enter_context(patch.object(door.lib, "CasinoPlayer", return_value=_player()))
        stack.enter_context(patch.object(door.lib, "runmodule", side_effect=runmodule))
        stack.enter_context(patch.object(door.io, "echo"))
        stack.enter_context(patch.object(door.auth, "disconnect"))
        stack.enter_context(patch.object(door.auth, "cleanup_remote_client_screen"))
        stack.enter_context(patch.object(door.auth, "init_remote_client_screen"))
        if menu_fn is not None:
            host.register_menu(menu_fn)
        else:
            stack.enter_context(patch.object(door.io, "inputchoice", side_effect=lambda *a, **k: answer_fn()))
        door.main(_args())
    return [m for m in dispatched if m != "startup"]


def test_hosted_quit_lowercase_ends_the_loop():
    calls = []

    def menu(prompt, registry, default="", help=None):
        calls.append(sorted(registry.keys()))
        return "q"

    dispatched = _run_door(None, menu_fn=menu)
    assert dispatched == []
    assert calls, "the door menu should have asked for a choice"
    assert "q" in calls[0] and "x" in calls[0]


def test_hosted_option_letter_dispatches_its_module():
    """Hosted returns lowercase. The unseated 'c' option (Connect) must dispatch 'auth'."""
    dispatched = []

    answers = iter(["c", "q"])

    def menu(prompt, registry, default="", help=None):
        return next(answers)

    with patch.object(door.auth, "connect", return_value=None) as connect:
        dispatched = _run_door(None, menu_fn=menu)
    assert connect.called, "hosted choice 'c' should run the auth connect step"


def test_standalone_uppercase_answer_dispatches_the_same_option():
    """Standalone io.inputchoice returns 'C'. It must dispatch the same as hosted 'c'.
    Before 8c the loop compared lowercase letters to 'C' and dispatched nothing."""
    answers = iter(["C", "Q"])
    with patch.object(door.auth, "connect", return_value=None) as connect:
        _run_door(lambda: next(answers))
    assert connect.called, "standalone choice 'C' should run the auth connect step"


def test_standalone_uppercase_quit_ends_the_loop():
    answers = iter(["Q"])
    dispatched = _run_door(lambda: next(answers))
    assert dispatched == []


def test_hosted_and_standalone_offer_the_same_letters():
    """The choice string is lowercase and the same letters are offered in both modes."""
    hosted_keys = []
    standalone = {}

    def menu(prompt, registry, default="", help=None):
        hosted_keys.append(sorted(registry.keys()))
        return "q"

    _run_door(None, menu_fn=menu)
    host.unregister_menu()

    def fake_inputchoice(prompt, options, default="", **kw):
        standalone["options"] = options
        return "Q"

    with patch.object(door.io, "inputchoice", side_effect=fake_inputchoice), \
         patch.object(door.io, "echo"), \
         patch.object(door.database, "getpool", return_value=_Pool()), \
         patch.object(door.session, "start", return_value=True), \
         patch.object(door.lib, "setbottombar"), \
         patch.object(door.lib, "_unregister_casino_fragments"), \
         patch.object(door.lib, "_clear_bottombar"), \
         patch.object(door.member, "getcurrentmoniker", return_value="alice"), \
         patch.object(door.lib, "CasinoPlayer", return_value=_player()), \
         patch.object(door.lib, "runmodule", return_value=True), \
         patch.object(door.auth, "disconnect"), \
         patch.object(door.auth, "init_remote_client_screen"), \
         patch.object(door.auth, "cleanup_remote_client_screen"):
        door.main(_args())

    assert hosted_keys, "hosted run should have built a registry"
    # inputchoice gets the same letters as a bare run, which the seam reads one per key.
    assert sorted(standalone["options"]) == sorted(hosted_keys[0])
