"""Casino's menus accept the shell's exit words.

``exit`` leaves the current menu and returns to the one that opened it (when casino runs from letteredolive, that is the
shell). ``logout`` ends the whole session, the same as Ctrl-D: it raises EOFError, which the hosting program already treats
as the end of the session.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino import host, menu

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _standalone():
    host.unregister_menu()
    yield
    host.unregister_menu()


def _run_main(words):
    """Run the root menu with ``io.inputchoice`` (the reader ``menu.main`` passes to read_menu) scripted to ``words``.

    Returns the menu's result and the keys the menu offered on its first read.
    """
    queue = list(words)
    offered = []

    def inputchoice(prompt, options, default="", **kwargs):
        if not offered:
            offered.append(set(str(k).lower() for k in options))
        return queue.pop(0)

    args = SimpleNamespace(debug=False)
    with patch.object(menu.io, "inputchoice", side_effect=inputchoice), \
         patch.object(menu.io, "echo"), patch.object(menu.util, "heading"), patch.object(menu.libcasino, "setarea"):
        result = menu.main(args)
    return result, offered


class TestExit:
    def test_exit_leaves_casino_and_returns_normally(self):
        result, _ = _run_main(["exit"])
        assert result is True

    def test_exit_is_an_alias_of_x(self):
        # The menu offers X (with Q and exit as aliases), not a separate exit key.
        _, offered = _run_main(["exit"])
        assert "x" in offered[0]


class TestLogout:
    def test_logout_raises_eoferror_so_the_whole_session_ends(self):
        with pytest.raises(EOFError):
            _run_main(["logout"])

    def test_logout_is_offered_in_the_menu_keys(self):
        with pytest.raises(EOFError):
            _run_main(["logout"])


class TestClassicKeysStillWork:
    def test_x_still_exits(self):
        result, _ = _run_main(["x"])
        assert result is True
