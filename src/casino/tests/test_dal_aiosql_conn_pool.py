"""Regression tests for the async DAL ``pool=`` keyword threading.

Every public function in ``casino.dal.aiosql.{bet,game,table}``
threads its optional ``pool`` argument into
``database.async_query``. The signature shape mirrors the sync
DAL regression test in ``test_dal_conn_pool.py``.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

import casino.dal.aiosql.bet as async_bet
import casino.dal.aiosql.game as async_game
import casino.dal.aiosql.table as async_table


SIGNATURE_SCAN = [
    (async_bet, "place_bet"),
    (async_bet, "settle_bet"),
    (async_bet, "update_bet_notes"),
    (async_bet, "update_bet_currenthand"),
    (async_bet, "get_player_bets"),
    (async_bet, "get_table_bets"),
    (async_bet, "update_bet_hand_id"),
    (async_bet, "get_bet_for_hand"),
    (async_game, "create_game"),
    (async_game, "get_active_game"),
    (async_game, "get_current_game"),
    (async_game, "update_game_status"),
    (async_game, "update_game_attrs"),
    (async_game, "get_game_hands"),
    (async_game, "create_hand"),
    (async_game, "update_hand_cards"),
    (async_game, "update_hand_status"),
    (async_game, "get_hand"),
    (async_game, "get_player_hand"),
    (async_game, "get_dealer_hand"),
    (async_game, "create_dealer_hand"),
    (async_game, "update_dealer_hand_cards"),
    (async_game, "get_or_create_dealer_hand"),
    (async_table, "create_table"),
    (async_table, "get_table_stats"),
    (async_table, "get_table"),
    (async_table, "list_tables"),
    (async_table, "get_table_players"),
    (async_table, "get_table_spectators"),
    (async_table, "add_player_to_table"),
    (async_table, "remove_player_from_table"),
    (async_table, "delete_table"),
    (async_table, "update_shoe"),
    (async_table, "update_table"),
    (async_table, "reset_shoe"),
    (async_table, "get_player_tables"),
]


def test_every_aiosql_function_accepts_pool_kwarg():
    """Every public async helper exposes ``pool=None``."""
    missing = []
    for module, name in SIGNATURE_SCAN:
        fn = getattr(module, name)
        sig = inspect.signature(fn)
        if "pool" not in sig.parameters:
            missing.append(f"{module.__name__}.{name}")
        elif sig.parameters["pool"].default is not None:
            missing.append(f"{module.__name__}.{name}: pool default != None")
    assert not missing, "missing or invalid pool kwarg: " + ", ".join(missing)


def test_pool_kwarg_is_keyword_only_in_aiosql():
    for module, name in SIGNATURE_SCAN:
        fn = getattr(module, name)
        sig = inspect.signature(fn)
        if "pool" not in sig.parameters:
            continue
        pool_param = sig.parameters["pool"]
        assert pool_param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"{module.__name__}.{name}.pool is not keyword-only"
        )
