"""The client menu has a help option, typed as help or ?, that prints the command list."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bbsengine6.menu_next import read_menu

from casino.client import menu as client_menu

pytestmark = pytest.mark.unit


def _client():
    return SimpleNamespace(moniker="jam", balance=0, current_table_moniker=None,
                           is_sysop=False, connected=True, authenticated=True)


@pytest.mark.parametrize("typed", ["help", "?"])
def test_help_and_question_mark_choose_the_help_option(typed):
    c = _client()
    ch = read_menu("p: ", client_menu._OPTIONS_SPEC, state=c,
                   check=client_menu._checker(c), reader=lambda p, **k: typed)
    assert ch.key == "help"


def test_question_mark_is_an_alias_of_help_in_the_spec():
    opt = next(o for o in client_menu._OPTIONS_SPEC if o.letter == "help")
    assert "?" in opt.aliases


def test_quit_is_unchanged():
    c = _client()
    ch = read_menu("p: ", client_menu._OPTIONS_SPEC, state=c,
                   check=client_menu._checker(c), reader=lambda p, **k: "quit")
    assert ch.key == "quit"


def test_typed_help_prints_the_f1_lines_without_the_word_help():
    # The typed command is already "help", so only the list prints; F1 keeps the word.
    from casino.client.casino_client import CasinoClient

    fake = SimpleNamespace(is_sysop=False, moniker="jam", balance=0,
                           current_table_moniker=None, connected=True, authenticated=True)
    f1_lines = client_menu._render_help(client=fake).split("\n")
    printed = []
    with patch("casino.client.casino_client.io.echo", side_effect=lambda t, *a, **k: printed.append(t)):
        CasinoClient._show_help(fake)
    assert f1_lines[0] == "help"
    assert printed == f1_lines[1:]
    assert "help" not in printed
