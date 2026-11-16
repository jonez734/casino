"""Every casino money move goes through the bank, and member.credits is never written.

A bet moves the stake from the player's bank account to the table's bank account (casino.__bank_table), with a
bank.__transaction row. A payout moves it back. The balance a player sees is their bank account. member.credits is
not read or written by any of these paths.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino.dal import bet as dal_bet
from casino.dal import player as dal_player


pytestmark = pytest.mark.unit


def test_a_bet_debits_the_player_bank_account_not_member_credits(monkeypatch):
    executed = []
    cur = MagicMock()
    cur.execute.side_effect = lambda q, p=None: executed.append(str(q))
    cur.fetchone.return_value = {"id": 1, "membermoniker": "alice", "cardtablemoniker": "blackjack-jam",
                                 "gameid": 1, "playermoniker": "alice", "amount": 10, "status": "pending",
                                 "dateposted": None}
    monkeypatch.setattr(dal_bet, "_bank_move", lambda *a, **k: executed.append("BANK_MOVE"))
    monkeypatch.setattr(dal_bet, "_connect_ctx", _ctx(cur, monkeypatch))
    dal_bet.place_bet(SimpleNamespace(), "alice", "blackjack-jam", 1, 10, pool=None)
    assert "BANK_MOVE" in executed, "the stake moves through the bank"
    assert not any("engine.__member" in q and "credits" in q for q in executed), "member.credits is not written"


def test_the_balance_is_the_bank_account_balance(monkeypatch):
    cur = MagicMock()
    cur.fetchone.return_value = {"balance": 90}
    monkeypatch.setattr(dal_player, "casino_conn", SimpleNamespace(connect=_ctx(cur, monkeypatch)))
    assert dal_player.get_player_balance(SimpleNamespace(), "alice") == 90
    sql = str(cur.execute.call_args.args[0])
    assert "bank.__account" in sql
    assert "engine.__member" not in sql


def test_the_mirror_from_credits_is_gone():
    assert not hasattr(dal_player, "mirror_credits_from_bank")


def _ctx(cur, monkeypatch=None):
    """A connection context and a cursor that yields ``cur``. Patched through monkeypatch so it is undone after the test."""
    from bbsengine6 import database

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _C:
        def __enter__(self):
            return cur

        def __exit__(self, *a):
            return False

    if monkeypatch is not None:
        monkeypatch.setattr(database, "cursor", lambda conn: _C())

    def connect(*a, **k):
        return _Conn()

    return connect
