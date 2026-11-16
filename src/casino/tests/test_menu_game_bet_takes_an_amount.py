"""The casino menu accepts ``game bet 10`` (an optional amount after bet), and still accepts a bare ``game bet``.

The menu validates a typed line against the subcommand's own parser. The ``bet`` subcommand had none, so any
trailing word was refused and the prompt came back. The amount must pass the same menu check the rest of the
line does.
"""

from types import SimpleNamespace

import pytest

from bbsengine6.menu_next.read import _accept, _index, _resolve

from casino.client import menu as m


pytestmark = pytest.mark.unit


def _state():
    return SimpleNamespace(current_table_moniker="blackjack-jam", current_table_game_type="blackjack",
                           is_sysop=False, owns_tables=False, moniker="jam", args=None, balance=100000)


def _allow(module_path, op):
    return True


def test_game_bet_with_an_amount_is_accepted():
    table = _index(m._OPTIONS_SPEC, _state(), _allow)
    assert _accept("game bet 10", table, _state(), _allow) is True


def test_a_bare_game_bet_is_still_accepted():
    table = _index(m._OPTIONS_SPEC, _state(), _allow)
    assert _accept("game bet", table, _state(), _allow) is True


def test_game_bet_with_a_non_number_is_refused():
    table = _index(m._OPTIONS_SPEC, _state(), _allow)
    assert _accept("game bet ten", table, _state(), _allow) is False


def test_the_amount_reaches_the_bet_namespace():
    table = _index(m._OPTIONS_SPEC, _state(), _allow)
    opt, sub, args = _resolve("game bet 10", table, _state(), _allow)
    assert sub == "bet" and args == ["10"]
