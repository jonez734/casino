#!/usr/bin/env python3
# casino/tests/test_client_list_players.py
# The P command lists a table's players. Each seat is labelled [BOT] or [HUMAN]; spectators are
# listed separately. The prompt defaults to the current table. No daemon: the table fetch is stubbed.

import inspect
from unittest.mock import MagicMock, patch

import pytest

from casino.client import casino_client as cc
from casino.client import menu


def _client(table, current=None):
    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client.current_table_moniker = current
    client._loop = MagicMock()
    client._fetch_table = MagicMock(return_value=table)
    return client


def _echoes(client, answer):
    out = []
    with patch.object(cc.io, "inputstring", return_value=answer), \
         patch.object(cc.io, "echo", side_effect=lambda *a, **k: out.append(str(a[0]) if a else "")):
        client.cmd_list_players()
    return "\n".join(out)


@pytest.mark.unit
def test_menu_offers_players_under_table():
    """Players is the ``view`` subcommand of the table entry, so it is reached by
    typing ``table view`` (or choosing it from the table submenu)."""
    spec = {opt.letter: opt for opt in menu._OPTIONS_SPEC}
    assert "view" in spec["table"].subcommands


@pytest.mark.unit
def test_every_seat_is_labelled_human_until_bots_exist():
    text = _echoes(_client({"players": ["alice", "bob"], "spectators": []}), "t1")
    assert "[HUMAN]" in text
    assert "[BOT]" not in text
    assert "alice" in text and "bob" in text


@pytest.mark.unit
def test_spectators_are_listed_separately_and_not_as_seats():
    text = _echoes(_client({"players": ["alice"], "spectators": ["carol"]}), "t1")
    assert "Spectators (not seated):" in text
    assert "carol" in text
    seat_line = [l for l in text.splitlines() if "alice" in l][0]
    assert "player" in seat_line
    assert "spectator" in [l for l in text.splitlines() if "carol" in l][0]


@pytest.mark.unit
def test_empty_table_says_no_one_is_seated():
    text = _echoes(_client({"players": [], "spectators": []}), "t1")
    assert "(no one seated)" in text


@pytest.mark.unit
def test_blank_answer_defaults_to_the_current_table():
    client = _client({"players": ["alice"], "spectators": []}, current="blackjack-jam")
    _echoes(client, "")
    client._fetch_table.assert_called_once_with("blackjack-jam")


@pytest.mark.unit
def test_missing_table_is_reported():
    client = _client(None)
    text = _echoes(client, "nope")
    assert "no table named nope" in text


@pytest.mark.unit
def test_dispatch_routes_table_view_to_the_listing():
    src = inspect.getsource(cc.CasinoClient._dispatch_table)
    assert '"view": ("View", self.cmd_list_players)' in src
