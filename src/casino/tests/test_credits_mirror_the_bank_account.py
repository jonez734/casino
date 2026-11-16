"""A member with no recorded credits takes its bank account's balance; a recorded value is never overwritten.

Bets and the balance read draw on member credits. A member whose credits were never set (NULL) but who has a bank
account gets its credits from that account. A member with credits already recorded is left alone.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bbsengine6 import database
from casino.dal import player as dal_player


pytestmark = pytest.mark.unit


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _text(query):
    """The statement as text: psycopg composes queries, so match on the rendered form."""
    import psycopg.sql as pgsql

    return pgsql.Composed([query]).as_string(None) if isinstance(query, pgsql.Composable) else str(query)


def _patch(monkeypatch, rowcount, calls):
    cur = MagicMock()
    cur.rowcount = rowcount

    def execute(sql, params=None):
        calls.append((sql, params))

    cur.execute.side_effect = execute
    monkeypatch.setattr(dal_player, "casino_conn", SimpleNamespace(connect=lambda *a, **k: _Conn()))
    monkeypatch.setattr(database, "cursor", lambda conn: _CurCtx(cur))
    return cur


class _CurCtx:
    def __init__(self, cur):
        self._cur = cur

    def __enter__(self):
        return self._cur

    def __exit__(self, *a):
        return False


def test_a_null_credits_member_takes_the_bank_balance(monkeypatch):
    calls = []
    _patch(monkeypatch, rowcount=1, calls=calls)
    assert dal_player.mirror_credits_from_bank(SimpleNamespace(), "alice") == 1
    sql = _text(calls[0][0])
    assert "credits IS NULL" in sql, "only a NULL credits value is set"
    assert "bank.__account" in sql


def test_a_recorded_credits_value_is_never_overwritten(monkeypatch):
    calls = []
    _patch(monkeypatch, rowcount=0, calls=calls)  # WHERE credits IS NULL matches nothing for a recorded member
    assert dal_player.mirror_credits_from_bank(SimpleNamespace(), "jam") == 0
    assert "credits IS NULL" in _text(calls[0][0])
