#!/usr/bin/env python3
# casino/tests/test_client_bottombar.py
# The bed client's bottom bar: left shows the seated table, right shows the moniker and bank
# balance. Fragments read the client's live state; the bar is attached in the menu loop.

import inspect
import types

from casino.client import bottombar as bar
from casino.client import casino_client as cc


def _client(**kw):
    base = dict(moniker="jam", balance=100000, authenticated=True, current_table_moniker=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_right_side_shows_moniker_and_balance():
    c = _client()
    bar.attach(lambda: c)
    try:
        assert bar._moniker_fragment() == "jam"
        assert bar._balance_fragment() == "bank 100000"
    finally:
        bar.detach()


def test_left_side_shows_the_seated_table_only_when_seated():
    c = _client()
    bar.attach(lambda: c)
    try:
        assert bar._table_left() == ""
        c.current_table_moniker = "blackjack-jam"
        assert bar._table_left() == "table: blackjack-jam"
    finally:
        bar.detach()


def test_balance_hidden_until_authenticated():
    c = _client(authenticated=False)
    bar.attach(lambda: c)
    try:
        assert bar._balance_fragment() == ""
    finally:
        bar.detach()


def test_fragments_follow_live_state_not_a_snapshot():
    c = _client()
    bar.attach(lambda: c)
    try:
        c.balance = 90000
        assert bar._balance_fragment() == "bank 90000"
    finally:
        bar.detach()


def test_attach_registers_and_detach_unregisters_the_fragments():
    c = _client()
    bar.attach(lambda: c)
    assert bar._moniker_fragment in bar._registry
    assert bar._balance_fragment in bar._registry
    bar.detach()
    assert bar._moniker_fragment not in bar._registry
    assert bar._balance_fragment not in bar._registry


def test_menu_loop_attaches_the_bar_and_detaches_on_exit():
    src = inspect.getsource(cc.CasinoClient.run)
    assert "_bar.attach(lambda: self)" in src
    assert "_bar.detach()" in src
    menu = inspect.getsource(cc.CasinoClient._run_menu_loop)
    assert "_bar.redraw()" in menu
