"""Enter on a blank line re-reads the client menu; it does not choose Quit.

The client menu used to pass default="quit" to read_menu, so an empty line selected Quit and ended
the client. The menu now has no default. A blank line is refused by the menu's verify and re-read
by the line reader; the word quit is still the exit.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bbsengine6.menu_next import read_menu

from casino.client import menu as client_menu

pytestmark = pytest.mark.unit


def _client():
    return SimpleNamespace(
        moniker="jam", balance=0, current_table_moniker=None, is_sysop=False,
        connected=True, authenticated=True,
    )


def _menu_with_lines(*lines):
    """Run the real client menu, with a line reader that honours verify and re-reads on refusal."""
    client = _client()
    remaining = list(lines)
    seen = []

    def reader(prompt, verify=None, **kwargs):
        while True:
            line = remaining.pop(0)
            seen.append(line)
            if verify is None or verify(line):
                return line

    with patch.object(client_menu._host, "read_line", side_effect=reader):
        return client_menu.menu(client), seen


def test_menu_has_no_default():
    import inspect

    assert not hasattr(client_menu, "_DEFAULT")
    assert "default=" not in inspect.getsource(client_menu.menu)


def test_blank_line_is_refused_and_the_menu_is_read_again():
    choice, seen = _menu_with_lines("", "quit")
    assert seen == ["", "quit"]
    assert choice.key == "quit"


def test_quit_still_exits_on_the_first_line():
    choice, seen = _menu_with_lines("quit")
    assert seen == ["quit"]
    assert choice.key == "quit"
