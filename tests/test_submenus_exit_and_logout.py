"""Casino's key-mode submenus take the shell's words, like the root menu.

``exit`` is an alias of X: it leaves the submenu and returns to the menu that opened it. ``logout`` ends the whole session:
it raises EOFError, which the hosting shell re-raises to its top level (the Ctrl-D path).

Each menu reads its key through ``host.choose``. The tests script that reader, and patch the menu's own work out.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino import host
from casino.commands.bank import lib as bank_lib
from casino.commands.game import lib as game_lib
from casino.commands.slots import lib as slots_lib
from casino.commands.tictactoe import lib as ttt_lib

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _standalone():
    host.unregister_menu()
    yield
    host.unregister_menu()


def _scripted(words):
    queue = list(words)

    def choose(prompt, options, default="", help=None, **_):
        return queue.pop(0)

    return choose


def _run(module, fn, words, **extra):
    """Call a submenu function with its reader scripted. ``extra`` patches the work the menu would do."""
    host.register_menu(_scripted(words))
    args = SimpleNamespace(debug=False, rounds=None)
    client = SimpleNamespace(authenticated=True, moniker="jam")
    with patch.object(module.io, "echo"):
        return fn(args, client=client, **extra)


SUBMENUS = [
    ("slots", slots_lib, "menu", {}),
    ("tictactoe", ttt_lib, "menu", {}),
    ("game", game_lib, "menu", {}),
    ("bank", bank_lib, "menu", {}),
]


@pytest.mark.parametrize("name,module,fn_name,extra", SUBMENUS, ids=[s[0] for s in SUBMENUS])
class TestSubmenus:
    def test_exit_returns_to_the_caller(self, name, module, fn_name, extra):
        # The menu reads ``exit`` once and returns. A reader that is asked again would raise (its queue is empty).
        fn = getattr(module, fn_name)
        asked = []

        def choose(prompt, options, default="", help=None, **_):
            asked.append(prompt)
            if len(asked) > 1:
                raise AssertionError("the menu asked again after exit")
            return "exit"

        host.register_menu(choose)
        args = SimpleNamespace(debug=False, rounds=None)
        client = SimpleNamespace(authenticated=True, moniker="jam")
        with patch.object(module.io, "echo"):
            fn(args, client=client, **extra)
        assert len(asked) == 1

    def test_logout_raises_eoferror_so_the_session_ends(self, name, module, fn_name, extra):
        fn = getattr(module, fn_name)
        with pytest.raises(EOFError):
            _run(module, fn, ["logout"], **extra)
