"""The casino root menu reads keys with menu_next key mode.

B runs blackjack, S shows stats, and X (or Q, its alias) exits. Enter takes X as the default.
Each option carries its own action; these tests replace the actions so blackjack never starts.
"""

import pytest

from bbsengine6.menu_next import MenuOption, read_menu

from casino import menu


pytestmark = pytest.mark.unit


class Keys:
    """A scripted key reader with the io.inputchoice call shape."""

    def __init__(self, *keys):
        self.keys = list(keys)

    def __call__(self, prompt, options, default="", **kwargs):
        return self.keys.pop(0)


def _spec(ran):
    return (
        MenuOption(letter="B", label="Blackjack", action=lambda a: ran.append("B")),
        MenuOption(letter="S", label="Stats", action=lambda a: ran.append("S")),
        MenuOption(letter="X", label="Exit", aliases=("Q",), action=lambda a: ran.append("X")),
    )


def test_root_menu_offers_b_s_and_x_with_q_as_its_alias():
    spec = menu.root_menu()
    letters = {o.letter for o in spec}
    assert letters == {"B", "S", "X"}
    exit_option = next(o for o in spec if o.letter == "X")
    assert "Q" in exit_option.aliases


@pytest.mark.parametrize("key", ["s", "S"])
def test_stats_key_runs_stats(key):
    ran = []
    choice = read_menu("p: ", _spec(ran), mode="key", default="X", reader=Keys(key))
    assert choice.key == "S"
    assert ran == ["S"]


@pytest.mark.parametrize("key", ["x", "X", "q", "Q"])
def test_exit_keys_run_the_exit_only(key):
    ran = []
    choice = read_menu("p: ", _spec(ran), mode="key", default="X", reader=Keys(key))
    assert choice.key == "X"
    assert ran == ["X"]


def test_enter_takes_the_default_exit():
    ran = []
    choice = read_menu("p: ", _spec(ran), mode="key", default="X", reader=Keys(""))
    assert choice.key == "X"
    assert ran == ["X"]


def test_root_menu_keys_are_refused_unless_offered(monkeypatch):
    """An unknown key rings and reads again, so the menu keeps running until an exit."""
    ran = []
    rang = []
    monkeypatch.setattr("bbsengine6.io.echo", lambda text="", **kw: rang.append(text))
    choice = read_menu("p: ", _spec(ran), mode="key", default="X", reader=Keys("z", "s"))
    assert choice.key == "S"
    assert any("{bell}" in str(t) for t in rang)
