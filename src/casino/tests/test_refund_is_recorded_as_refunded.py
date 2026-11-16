"""A refunded bet is recorded as 'refunded', not 'won'.

A refund returns the full stake when a hand is removed from a round: the round clock's ``remove`` penalty,
and a stale round closed before a new bet. Money is unchanged. Only the recorded status changes.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino.dal import bet as dal_bet
from casino.dal import game as dal_game
from casino.services import game as game_mod
from casino.services import round_clock as rc


pytestmark = pytest.mark.unit


def test_refund_records_refunded_and_returns_the_stake():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    settle = MagicMock()
    with patch.object(dal_bet, "settle_bet", settle):
        svc._refund_bet({"id": 9, "amount": 5})
    assert settle.call_args.kwargs.get("status") == "refunded"
    assert settle.call_args.args[3] == 5


def test_round_clock_remove_penalty_records_refunded(monkeypatch):
    settle = MagicMock()
    monkeypatch.setattr(dal_bet, "settle_bet", settle)
    monkeypatch.setattr(dal_game, "update_hand_status", lambda *a, **k: None)
    rc._refund_standup_bet(SimpleNamespace(), {"id": 11, "amount": 7}, pool=None)
    assert settle.call_args.kwargs.get("status") == "refunded"
    assert settle.call_args.args[3] == 7
