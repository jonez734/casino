"""A member with no recorded credits is an error, never a silent zero.

The bet and balance reads treated a NULL credits value as 0, so a bet was refused as "Insufficient funds" while the
display showed a different balance. A missing value is now reported as such.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bbsengine6 import database
from casino.dal import bet as dal_bet
from casino.dal import player as dal_player


pytestmark = pytest.mark.unit


def _cursor_returning(row):
    cur = MagicMock()
    cur.fetchone.return_value = row
    return cur


def test_a_bet_with_null_credits_raises_a_clear_error_not_insufficient_funds(monkeypatch):
    cur = _cursor_returning({"credits": None})
    monkeypatch.setattr(dal_bet, "_connect_ctx", _ctx(cur))
    monkeypatch.setattr(database, "cursor", lambda conn: _Cursor(cur))
    monkeypatch.setattr(dal_player, "mirror_credits_from_bank", lambda *a, **k: 0)
    with pytest.raises(ValueError, match="no credits recorded for alice"):
        dal_bet.place_bet(SimpleNamespace(), "alice", "blackjack-jam", 1, 10, pool=None)


def test_a_balance_read_with_null_credits_raises_not_zero(monkeypatch):
    cur = _cursor_returning({"credits": None})
    monkeypatch.setattr(dal_player, "casino_conn", SimpleNamespace(connect=_ctx(cur)))
    monkeypatch.setattr(database, "cursor", lambda conn: _Cursor(cur))
    with pytest.raises(ValueError, match="no credits recorded for alice"):
        dal_player.get_player_balance(SimpleNamespace(), "alice")


def _ctx(cur):
    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self, *a, **k):
            return cur

    def connect(*a, **k):
        return _Conn()

    return connect


class _Cursor:
    def __init__(self, cur):
        self._cur = cur

    def __enter__(self):
        return self._cur

    def __exit__(self, *a):
        return False
