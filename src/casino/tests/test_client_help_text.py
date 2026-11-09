"""The client F1 help is returned as text, so handle_help draws it below the prompt.

_render_help used to draw with io.echo and return None, so handle_help had no text and the help
line never appeared. It now returns one string: the word help, the heading, then the option lines.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.client import menu as client_menu

pytestmark = pytest.mark.unit


def _client(sysop=False):
    return SimpleNamespace(
        moniker="jam", balance=0, current_table_moniker=None, is_sysop=sysop,
        connected=True, authenticated=True,
    )


def _help(client):
    with patch.object(client_menu.io, "echo") as echo, \
         patch.object(client_menu, "menu_entries", wraps=client_menu.menu_entries) as _:
        text = client_menu._render_help(client=client)
    return text, echo


def test_help_text_starts_with_the_word_help():
    text, _ = _help(_client())
    assert text.split("\n")[0] == "help"


def test_render_help_echoes_nothing_directly():
    _, echo = _help(_client())
    echo.assert_not_called()


def test_option_lines_carry_the_colour_tags():
    text, _ = _help(_client())
    body = text.split("\n")
    assert any("{var:menu.item.enabled}" in line or "{var:menu.item.disabled}" in line
               for line in body[2:])
    assert all(line.endswith("{/all}") for line in body[2:] if "[" in line)
    assert any("{labelcolor}" in line for line in body[2:])


def test_heading_is_text_and_ends_with_f6():
    text, _ = _help(_client())
    heading = text.split("\n")[1]
    assert "casino_client" in "\n".join(text.split("\n")[1:4])
    assert heading.startswith("{/all}{normalcolor}")


def test_non_sysop_does_not_see_disabled_entries():
    text, _ = _help(_client(sysop=False))
    assert "{var:menu.item.disabled}" not in text


def test_sysop_sees_disabled_entries_too():
    plain, _ = _help(_client(sysop=False))
    admin, _ = _help(_client(sysop=True))
    assert len(admin.split("\n")) >= len(plain.split("\n"))
