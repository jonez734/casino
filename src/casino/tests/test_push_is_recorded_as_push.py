"""A push is recorded as 'push' in the bet log, not as 'won'.

A push returns the stake, so its payout is positive; recording it as won made a 21-vs-21 tie read as a win.
Money is unchanged (the stake is returned). Only the recorded status changes. Tests use stand-ins; no
database is opened.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino.dal import bet as dal_bet
from casino.services import game as game_mod


pytestmark = pytest.mark.unit


def _service():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    return svc


def test_a_push_records_push_status_and_returns_the_stake():
    svc = _service()
    settle = MagicMock()
    with patch.object(dal_bet, "settle_bet", settle):
        svc._settle_bet_for_outcome(bet={"id": 3, "amount": 5}, outcome="push", payout=5)
    settle.assert_called_once()
    assert settle.call_args.kwargs.get("status") == "push"
    assert settle.call_args.args[3] == 5  # the stake is still returned


def test_a_win_still_records_won():
    svc = _service()
    settle = MagicMock()
    with patch.object(dal_bet, "settle_bet", settle):
        svc._settle_bet_for_outcome(bet={"id": 4, "amount": 5}, outcome="win", payout=10)
    assert settle.call_args.kwargs.get("status") == "won"


def test_a_loss_still_records_lost():
    svc = _service()
    settle = MagicMock()
    with patch.object(dal_bet, "settle_bet", settle):
        svc._settle_bet_for_outcome(bet={"id": 5, "amount": 5}, outcome="bust", payout=0)
    assert settle.call_args.kwargs.get("status") == "lost"
