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


# Phase 6: the bar must fit the terminal. The right side (moniker and bank balance) was never
# trimmed, so a long moniker or a large balance wrapped the bottom row on a narrow terminal.

import re as _re
from unittest.mock import patch as _patch

from bbsengine6 import bottombar as _bb


def _emitted_line(width, **kw):
    captured = []

    def fake_echo(text, **_):
        captured.append(text)

    c = _client(**kw)
    with _patch.object(_bb, "echo", fake_echo), _patch.object(_bb.terminal, "width", lambda: width):
        bar.attach(lambda: c)
        try:
            bar.redraw()
        finally:
            bar._provider = None
    return captured[-1]


def _visible(text):
    # Strip markup tokens such as {bottombarcolor}, and the ESC 7 / ESC 8 save and restore
    # codes the bar wraps itself in. Neither is drawn, so what remains is what is on screen.
    text = _re.sub(r"\{[^}]*\}", "", text)
    return _re.sub(r"\x1b[78]", "", text)


def test_bar_never_wider_than_the_terminal_with_a_long_right_side():
    for width in (30, 40, 60, 80):
        line = _visible(_emitted_line(
            width, moniker="a" * 40, balance=123456789, current_table_moniker="blackjack-x",
            current_table_game_type="blackjack",
        ))
        assert len(line) <= width - 2, (width, len(line), line)


def test_bar_keeps_the_balance_visible_when_it_must_trim():
    line = _visible(_emitted_line(
        40, moniker="a" * 35, balance=123456, current_table_moniker="blackjack-x",
        current_table_game_type="blackjack",
    ))
    assert line.endswith("bank 123456")


def test_bar_fits_at_normal_widths_with_a_long_table_name():
    for width in (40, 60, 80, 120):
        line = _visible(_emitted_line(
            width, moniker="jam", balance=100, current_table_moniker="blackjack-" + "y" * 70,
            current_table_game_type="blackjack",
        ))
        assert len(line) <= width - 2
