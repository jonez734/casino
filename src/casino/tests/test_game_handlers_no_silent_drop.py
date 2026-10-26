#!/usr/bin/env python3
# casino/tests/test_game_handlers_no_silent_drop.py
# A yahtzee or tictactoe type the handler claims but cannot route gets an explicit
# unhandled_type error, never None (a None is a silent drop: the client waits forever).
# Unclaimed types still return None so the router can try the next service.

import asyncio
from unittest.mock import MagicMock

import pytest

from casino.tictactoe.api_handler import TictactoeServiceHandler
from casino.yahtzee.api_handler import YahtzeeServiceHandler


def _ws_state(handler):
    """Make _check_access succeed so the request reaches the branch chain."""
    state = MagicMock()
    state.moniker = "jam"
    handler._check_access = MagicMock(return_value=(state, None))
    return handler


@pytest.mark.unit
@pytest.mark.parametrize("cls,claimed", [
    (YahtzeeServiceHandler, "yahtzee_quick_play"),
    (TictactoeServiceHandler, "tictactoe_quick_play"),
])
def test_claimed_type_with_no_branch_gets_an_explicit_error(cls, claimed):
    h = _ws_state(cls.__new__(cls))
    # Remove the branch-matching: simulate a claimed type no branch handles.
    cls_attr = "YAHTZEE_MSG_TYPES" if cls is YahtzeeServiceHandler else "TICTACTOE_MSG_TYPES"
    original = getattr(cls, cls_attr)
    setattr(cls, cls_attr, original + ("ghost_game_type",))
    try:
        out = asyncio.run(h.handle_message(None, MagicMock(), "/", {"type": "ghost_game_type"}))
    finally:
        setattr(cls, cls_attr, original)
    assert out is not None, "a claimed type must not be dropped with no reply"
    assert out["type"] == "error"
    assert out["code"] == "unhandled_type"
    assert "ghost_game_type" in out["message"]


@pytest.mark.unit
@pytest.mark.parametrize("cls", [YahtzeeServiceHandler, TictactoeServiceHandler])
def test_unclaimed_type_still_returns_none(cls):
    h = _ws_state(cls.__new__(cls))
    out = asyncio.run(h.handle_message(None, MagicMock(), "/", {"type": "bank_balance"}))
    assert out is None
