"""The game and bank submenus read keys with menu_next key mode, through host.choose.

Each option runs its handler with the menu's client and kwargs. X is the exit and runs nothing; Q is
an alias of X for backward compatibility. The handlers are replaced, so no game or bank call is made.
"""

import pathlib

import pytest

from bbsengine6.menu_next import read_menu

from casino import host
from casino.commands.bank import lib as bank
from casino.commands.game import lib as game


pytestmark = pytest.mark.unit


class Keys:
    def __init__(self, *keys):
        self.keys = list(keys)

    def __call__(self, prompt, options, default="", **kwargs):
        return self.keys.pop(0)


def _ran_spec(builder, ran, monkeypatch, module, names):
    """Replace each handler in ``module`` with a recorder, then build the menu's spec."""
    for name in names:
        monkeypatch.setattr(module, name, lambda a, client=None, _n=name, **kw: ran.append(_n))
    return builder(None, client="client")


GAME = {"B": "bet", "H": "hit", "S": "stand", "D": "double", "P": "play", "L": "split"}
BANK = {"B": "bank_balance", "A": "bank_add", "W": "bank_remove", "T": "bank_transfer",
        "P": "bank_pending", "H": "bank_history", "L": "bank_list_all"}


@pytest.mark.parametrize("key,handler", sorted(GAME.items()))
def test_game_key_runs_its_handler(key, handler, monkeypatch):
    ran = []
    spec = _ran_spec(game.game_menu, ran, monkeypatch, game, GAME.values())
    choice = read_menu("p", spec, mode="key", default="X", reader=Keys(key))
    assert choice.key == key
    assert ran == [handler]


@pytest.mark.parametrize("key,handler", sorted(BANK.items()))
def test_bank_key_runs_its_handler(key, handler, monkeypatch):
    ran = []
    spec = _ran_spec(bank.bank_menu, ran, monkeypatch, bank, BANK.values())
    choice = read_menu("p", spec, mode="key", default="X", reader=Keys(key))
    assert choice.key == key
    assert ran == [handler]


@pytest.mark.parametrize("builder,module,names", [
    (game.game_menu, game, GAME.values()),
    (bank.bank_menu, bank, BANK.values()),
])
@pytest.mark.parametrize("key", ["x", "X", "q", "Q"])
def test_exit_keys_exit_and_run_no_handler(builder, module, names, key, monkeypatch):
    """X exits, and Q still exits as its alias."""
    ran = []
    spec = _ran_spec(builder, ran, monkeypatch, module, names)
    choice = read_menu("p", spec, mode="key", default="X", reader=Keys(key))
    assert choice.key == "X"
    assert ran == []


@pytest.mark.parametrize("builder,module,names", [
    (game.game_menu, game, GAME.values()),
    (bank.bank_menu, bank, BANK.values()),
])
def test_enter_takes_x(builder, module, names, monkeypatch):
    ran = []
    spec = _ran_spec(builder, ran, monkeypatch, module, names)
    choice = read_menu("p", spec, mode="key", default="X", reader=Keys(""))
    assert choice.key == "X"
    assert ran == []


def test_submenus_read_through_the_host_reader(monkeypatch):
    """The reader is host.choose, so a hosted program still receives the key request."""
    seen = []

    def fake_choose(prompt, options, default="", help=None, **kw):
        seen.append(options)
        return default

    monkeypatch.setattr(host, "choose", fake_choose)
    read_menu("p", game.game_menu(None, client="c"), mode="key", default="X", reader=host.choose)
    # Q is accepted as an alias of X, so it is in the accepted keys. The menu shows only X.
    assert seen and set(seen[0]) >= set("BDHLPSX")
    source = pathlib.Path(game.__file__).read_text()
    assert "[X] Exit: " in source
    assert "[Q]uit" not in source


@pytest.mark.parametrize("module", [game, bank])
def test_prompt_shows_x_and_not_q(module):
    source = pathlib.Path(module.__file__).read_text()
    assert "[X] Exit: " in source
    assert "[Q]uit" not in source


def test_root_prompt_shows_x_and_not_q():
    from casino import menu

    source = pathlib.Path(menu.__file__).read_text()
    assert "[BSX]" in source
    assert "[BSXQ]" not in source
