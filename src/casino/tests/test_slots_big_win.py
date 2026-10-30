"""A big slots win is shouted to every player on casino:global.

Covers the decision (is_big_win), and the handler's behaviour around it:
  - a spin at or over BIG_WIN_MULTIPLIER is announced once, on casino:global, with the
    winner, table, bet, payout, and multiplier;
  - an ordinary spin is not announced;
  - the announcement is server-originated (no sender), so the announce-only check does not
    refuse it;
  - a failed announcement does not fail the spin.
"""

from __future__ import annotations

import argparse
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bbsengine6.net import ChannelState
from casino.api.handler import SlotServiceHandler
from casino.slots.lib import BIG_WIN_MULTIPLIER, is_big_win
from casino.tests._session_mock import make_sessions_mock


pytestmark = pytest.mark.unit


def test_threshold_is_a_multiple_of_the_bet():
    assert is_big_win(10, 10 * BIG_WIN_MULTIPLIER) is True
    assert is_big_win(10, 10 * BIG_WIN_MULTIPLIER - 1) is False


def test_no_bet_or_no_payout_is_never_a_big_win():
    assert is_big_win(0, 10_000) is False
    assert is_big_win(10, 0) is False
    assert is_big_win(-5, 10_000) is False


def test_threshold_follows_the_argument():
    assert is_big_win(10, 100, multiplier=10) is True
    assert is_big_win(10, 90, multiplier=10) is False


def _handler(state: ChannelState) -> SlotServiceHandler:
    args = argparse.Namespace(databasename="zoid6test", database="zoid6test")
    sessions = make_sessions_mock(moniker="alice", table_moniker="slots-big")
    h = SlotServiceHandler(args, sessions, channel_state=state)
    h.allow_legacy_session_only = True
    return h


def _spin_result(bet: int, payout: int) -> dict:
    return {
        "success": True,
        "spin": {
            "id": 42, "bet": bet, "payout": payout, "net": payout - bet,
            "reels": [], "center_row": [], "wins": [],
        },
    }


def _run_spin(bet: int, payout: int):
    """Run one spin through the real handler. Returns (reply, global_publishes, table_publishes)."""
    state = ChannelState()
    h = _handler(state)
    ws = MagicMock()
    ws.id = 1
    server = AsyncMock()
    globals_, tables = [], []

    async def capture_global(self_, server_, message, sender_moniker):
        globals_.append((message, sender_moniker))

    async def capture_table(self_, server_, table, message, sender_moniker):
        tables.append((table, message))

    with patch.object(h, "_handle_spin", return_value=_spin_result(bet, payout)), \
         patch.object(h, "_check_access", return_value=(MagicMock(moniker="alice"), None)), \
         patch.object(SlotServiceHandler, "_publish_global", capture_global), \
         patch.object(SlotServiceHandler, "_publish_to_table", capture_table):
        reply = asyncio.run(h._handle_spin_msg(
            ws, {"type": "slot_spin", "bet": bet, "table_moniker": "slots-big"}, server,
        ))
    return reply, globals_, tables


def test_a_big_win_is_shouted_once_on_the_global_channel():
    reply, globals_, _ = _run_spin(bet=10, payout=10 * 145)
    assert reply["type"] == "slot_result"
    assert len(globals_) == 1
    message, sender = globals_[0]
    assert message["type"] == "big_win"
    assert message["player_moniker"] == "alice"
    assert message["table_moniker"] == "slots-big"
    assert message["game_type"] == "slots"
    assert message["bet"] == 10
    assert message["payout"] == 1450
    assert message["multiplier"] == 145


def test_the_shout_is_server_originated_so_no_sender_is_attached():
    _, globals_, _ = _run_spin(bet=10, payout=10 * 145)
    _, sender = globals_[0]
    assert sender is None


def test_an_ordinary_win_is_not_shouted():
    _, globals_, _ = _run_spin(bet=10, payout=20)
    assert globals_ == []


def test_a_loss_is_not_shouted():
    _, globals_, _ = _run_spin(bet=10, payout=0)
    assert globals_ == []


def test_a_big_win_still_reaches_the_table_as_before():
    _, _, tables = _run_spin(bet=10, payout=10 * 145)
    assert len(tables) == 1
    table, message = tables[0]
    assert table == "slots-big"
    assert message["type"] == "slot_result"


def test_a_failed_shout_does_not_fail_the_spin():
    state = ChannelState()
    h = _handler(state)
    ws = MagicMock()
    ws.id = 1

    async def boom(self_, server_, message, sender_moniker):
        raise RuntimeError("channel unavailable")

    with patch.object(h, "_handle_spin", return_value=_spin_result(10, 10 * 145)), \
         patch.object(h, "_check_access", return_value=(MagicMock(moniker="alice"), None)), \
         patch.object(SlotServiceHandler, "_publish_global", boom), \
         patch.object(SlotServiceHandler, "_publish_to_table", AsyncMock()):
        reply = asyncio.run(h._handle_spin_msg(
            ws, {"type": "slot_spin", "bet": 10, "table_moniker": "slots-big"}, AsyncMock(),
        ))
    assert reply["type"] == "slot_result"
    assert reply["spin"]["payout"] == 1450


def _run_spin_with_config(bet: int, payout: int, slots_block: dict | None):
    """Run one spin with a given casino.slots.big_win block in the args' config."""
    args = argparse.Namespace(databasename="zoid6test", database="zoid6test")
    if slots_block is not None:
        args._casino_config = {"slots": {"big_win": slots_block}}
    state = ChannelState()
    sessions = make_sessions_mock(moniker="alice", table_moniker="slots-big")
    h = SlotServiceHandler(args, sessions, channel_state=state)
    h.allow_legacy_session_only = True
    ws = MagicMock()
    ws.id = 1
    globals_ = []

    async def capture_global(self_, server_, message, sender_moniker):
        globals_.append(message)

    with patch.object(h, "_handle_spin", return_value=_spin_result(bet, payout)), \
         patch.object(h, "_check_access", return_value=(MagicMock(moniker="alice"), None)), \
         patch.object(SlotServiceHandler, "_publish_global", capture_global), \
         patch.object(SlotServiceHandler, "_publish_to_table", AsyncMock()):
        asyncio.run(h._handle_spin_msg(
            ws, {"type": "slot_spin", "bet": bet, "table_moniker": "slots-big"}, AsyncMock(),
        ))
    return globals_


def test_disabled_in_config_means_no_shout_even_for_a_huge_win():
    assert _run_spin_with_config(10, 10 * 145, {"enabled": False}) == []


def test_a_configured_multiplier_moves_the_threshold():
    # 20x is a big win under a 20x threshold, and not under the default 50x.
    assert len(_run_spin_with_config(10, 10 * 20, {"multiplier": 20})) == 1
    assert _run_spin_with_config(10, 10 * 20, None) == []


def test_missing_config_uses_the_defaults():
    assert len(_run_spin_with_config(10, 10 * 145, None)) == 1
