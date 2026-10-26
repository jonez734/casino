#!/usr/bin/env python3
# casino/tests/test_round_clock.py
# The blackjack round clock (Phase 1a): one deadline per round, the skip and remove penalties,
# bots are never clocked, and every expired action is refused before it is applied.
# Database access is stubbed; nothing connects.

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino.services import round_clock as rc
from casino.services import game as gamemod
from casino.dal import bet as dal_bet_mod
from casino.dal import game as dal_game_mod
from casino.dal import table as dal_table_mod

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_clock_is_off_when_turn_seconds_is_zero():
    assert rc.deadline_for(0, now=NOW) is None
    assert rc.is_expired(None, now=NOW) is False


@pytest.mark.unit
def test_deadline_is_turn_seconds_after_the_round_opens():
    assert rc.deadline_for(30, now=NOW) == NOW + timedelta(seconds=30)


@pytest.mark.unit
def test_expires_at_the_deadline_not_before():
    deadline = NOW + timedelta(seconds=30)
    assert rc.is_expired(deadline, now=NOW + timedelta(seconds=29)) is False
    assert rc.is_expired(deadline, now=NOW + timedelta(seconds=30)) is True


@pytest.mark.unit
@pytest.mark.parametrize("table,expected", [
    ({"clock_penalty": "skip"}, "skip"),
    ({"clock_penalty": "remove"}, "remove"),
    ({"clock_penalty": "bogus"}, "skip"),
    ({}, "skip"),
])
def test_penalty_is_skip_or_remove_with_skip_as_the_default(table, expected):
    assert rc.penalty_for(table) == expected


@pytest.mark.unit
def test_bots_are_never_clocked():
    assert rc.is_bot_seat({"is_bot": True}) is True
    assert rc.is_bot_seat({"is_bot": False}) is False
    assert rc.is_bot_seat({}) is False


def _service(game=None, hands=None, deadline=None, table=None):
    svc = gamemod.GameService.__new__(gamemod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    svc.settle_game = MagicMock(return_value={"success": True})
    return svc


@pytest.mark.unit
def test_expired_round_refuses_hit_before_any_card_is_drawn():
    svc = _service()
    game = {"id": 7}
    with patch.object(gamemod.dal_game, "get_active_game", return_value=game), \
         patch.object(gamemod.dal_game, "get_action_deadline", return_value=NOW - timedelta(seconds=1)), \
         patch.object(rc, "expire_round", return_value={"success": True}) as expire, \
         patch.object(gamemod.dal_game, "get_player_hand") as get_hand:
        out = svc.hit("t1", "alice")
    assert out == {"success": False, "message": "The round clock expired"}
    expire.assert_called_once()
    get_hand.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize("action", ["stand", "double", "split", "surrender"])
def test_every_action_is_refused_after_the_clock_runs_out(action):
    svc = _service()
    game = {"id": 7}
    with patch.object(gamemod.dal_game, "get_active_game", return_value=game), \
         patch.object(gamemod.dal_game, "get_action_deadline", return_value=NOW - timedelta(seconds=1)), \
         patch.object(rc, "expire_round", return_value={"success": True}):
        out = getattr(svc, action)("t1", "alice")
    assert out.get("success") is False
    assert out.get("message") == "The round clock expired"


@pytest.mark.unit
def test_a_running_clock_does_not_block_an_action():
    svc = _service()
    game = {"id": 7}
    real_now = datetime.now(timezone.utc)
    with patch.object(gamemod.dal_game, "get_active_game", return_value=game), \
         patch.object(gamemod.dal_game, "get_action_deadline", return_value=real_now + timedelta(hours=1)), \
         patch.object(rc, "expire_round") as expire:
        assert svc._round_expired("t1", game) is False
    expire.assert_not_called()


@pytest.mark.unit
def test_expire_round_remove_returns_the_stake_and_marks_the_hand_removed():
    svc = _service()
    hand = {"id": 11, "playermoniker": "alice", "is_bot": False}
    bet = {"id": 99, "amount": 25, "status": "pending"}
    with patch.object(dal_game_mod, "get_active_game", return_value={"id": 7}), \
         patch.object(dal_table_mod, "get_table", return_value={"clock_penalty": "remove"}), \
         patch.object(dal_game_mod, "get_game_hands", return_value=[hand]), \
         patch.object(dal_bet_mod, "get_bet_for_hand", return_value=bet), \
         patch.object(dal_bet_mod, "settle_bet") as settle, \
         patch.object(dal_game_mod, "update_hand_status") as status, \
         patch.object(rc, "log_expiry") as log:
        out = rc.expire_round(svc, "t1")
    settle.assert_called_once_with(svc.args, 99, True, 25, pool=None)
    status.assert_called_once_with(svc.args, 11, "removed", pool=None)
    log.assert_called_once()
    assert out == {"success": True, "expired": 1, "penalty": "remove"}


@pytest.mark.unit
def test_expire_round_skip_leaves_the_hand_on_its_cards():
    svc = _service()
    hand = {"id": 11, "playermoniker": "alice"}
    bet = {"id": 99, "amount": 25, "status": "pending"}
    with patch.object(dal_game_mod, "get_active_game", return_value={"id": 7}), \
         patch.object(dal_table_mod, "get_table", return_value={"clock_penalty": "skip"}), \
         patch.object(dal_game_mod, "get_game_hands", return_value=[hand]), \
         patch.object(dal_bet_mod, "get_bet_for_hand", return_value=bet), \
         patch.object(dal_bet_mod, "settle_bet") as settle, \
         patch.object(dal_game_mod, "update_hand_status") as status, \
         patch.object(rc, "log_expiry"):
        out = rc.expire_round(svc, "t1")
    settle.assert_not_called()
    status.assert_not_called()
    svc.settle_game.assert_called_once_with("t1")
    assert out["penalty"] == "skip"


@pytest.mark.unit
def test_expire_round_never_touches_a_bot_hand():
    svc = _service()
    hand = {"id": 11, "playermoniker": "botty", "is_bot": True}
    with patch.object(dal_game_mod, "get_active_game", return_value={"id": 7}), \
         patch.object(dal_table_mod, "get_table", return_value={"clock_penalty": "remove"}), \
         patch.object(dal_game_mod, "get_game_hands", return_value=[hand]), \
         patch.object(dal_bet_mod, "get_bet_for_hand") as get_bet, \
         patch.object(rc, "log_expiry") as log:
        out = rc.expire_round(svc, "t1")
    get_bet.assert_not_called()
    log.assert_not_called()
    assert out["expired"] == 0
