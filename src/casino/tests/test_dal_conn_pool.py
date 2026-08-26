"""Regression tests for the DAL ``pool=`` keyword threading (CONN_POOL_PATTERN).

Every public function in
``casino.dal.{bet,game,table}`` and the async mirror
``casino.dal.aiosql.{bet,game,table}`` accepts an optional
``pool`` keyword. When supplied, the function threads it into
``database.connect(args, pool=pool)`` /
``database.async_query(args, sql, pool=pool, ...)``. When absent,
the legacy ``database.connect(args)`` /
``database.async_query(args, sql, ...)`` shape is preserved so
callers we don't reach keep working.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

import casino.dal.bet as dal_bet
import casino.dal.game as dal_game
import casino.dal.table as dal_table


SIGNATURE_SCAN = [
    # (module, fn-name)
    (dal_bet, "place_bet"),
    (dal_bet, "settle_bet"),
    (dal_bet, "set_insurance"),
    (dal_bet, "get_insurance"),
    (dal_bet, "settle_insurance"),
    (dal_bet, "update_bet_notes"),
    (dal_bet, "update_bet_currenthand"),
    (dal_bet, "get_player_bet_for_game"),
    (dal_bet, "get_player_bets"),
    (dal_bet, "get_table_bets"),
    (dal_bet, "place_split_bet"),
    (dal_bet, "double_bet"),
    (dal_bet, "update_bet_hand_id"),
    (dal_bet, "get_bet_for_hand"),
    (dal_bet, "get_hand_bets"),
    (dal_game, "create_game"),
    (dal_game, "get_active_game"),
    (dal_game, "get_current_game"),
    (dal_game, "update_game_status"),
    (dal_game, "update_game_attrs"),
    (dal_game, "get_game_hands"),
    (dal_game, "create_hand"),
    (dal_game, "update_hand_cards"),
    (dal_game, "update_hand_status"),
    (dal_game, "update_hand_attrs"),
    (dal_game, "get_hand"),
    (dal_game, "get_player_hand"),
    (dal_game, "get_player_hands"),
    (dal_game, "get_dealer_hand"),
    (dal_game, "create_dealer_hand"),
    (dal_game, "update_dealer_hand_cards"),
    (dal_game, "get_dealer_hole_card"),
    (dal_game, "set_dealer_hole_card"),
    (dal_game, "reveal_dealer_hole_card"),
    (dal_game, "get_or_create_dealer_hand"),
    (dal_table, "create_table"),
    (dal_table, "get_table"),
    (dal_table, "list_tables"),
    (dal_table, "get_table_players"),
    (dal_table, "get_table_spectators"),
    (dal_table, "add_player_to_table"),
    (dal_table, "remove_player_from_table"),
    (dal_table, "delete_table"),
    (dal_table, "update_shoe"),
    (dal_table, "update_table"),
    (dal_table, "reset_shoe"),
    (dal_table, "get_table_stats"),
    (dal_table, "_stats_from_slot_spins"),
    (dal_table, "_stats_from_blackjack_games"),
    (dal_table, "_stats_from_settled_games"),
    (dal_table, "_stats_from_poker_games"),
]


def test_every_dal_function_accepts_pool_kwarg():
    """Every public/internal DAL helper exposes ``pool=None``.

    The contract that commit 2 establishes: callers can opt into
    CONN_POOL_PATTERN by passing ``pool=`` to any DAL helper.
    """
    missing = []
    for module, name in SIGNATURE_SCAN:
        fn = getattr(module, name)
        sig = inspect.signature(fn)
        if "pool" not in sig.parameters:
            missing.append(f"{module.__name__}.{name}")
        elif sig.parameters["pool"].default is not None:
            missing.append(f"{module.__name__}.{name}: pool default != None")
    assert not missing, "missing or invalid pool kwarg in: " + ", ".join(missing)


def test_pool_kwarg_is_keyword_only():
    """CONN_POOL_PATTERN requires ``pool=`` as a keyword-only arg."""
    for module, name in SIGNATURE_SCAN:
        fn = getattr(module, name)
        sig = inspect.signature(fn)
        if "pool" not in sig.parameters:
            continue
        pool_param = sig.parameters["pool"]
        assert pool_param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"{module.__name__}.{name}.pool is not keyword-only "
            f"({pool_param.kind.name})"
        )


def test_update_table_pool_kwarg_is_before_var_keyword():
    """``update_table`` forwards ``**updates`` so ``pool=`` must be keyword-only."""
    sig = inspect.signature(dal_table.update_table)
    params = list(sig.parameters.values())
    pool_param = next(p for p in params if p.name == "pool")
    var_kw_param = next(p for p in params if p.kind == inspect.Parameter.VAR_KEYWORD)
    pool_index = params.index(pool_param)
    var_kw_index = params.index(var_kw_param)
    assert pool_index < var_kw_index, "pool must precede **updates so callers can pass both"


class TestPoolCallThroughOnSelect:
    """For a read-only DAL function, when ``pool`` is supplied the
    function threads it into ``database.connect``.

    Patches the module-level ``database`` import so we can assert
    the connection call shape without a live PG.
    """

    def test_get_table_threads_pool_into_connect(self, monkeypatch):
        captured = {}

        class _ConnCM:
            def __enter__(self_inner):
                captured["conn_entered"] = True
                return MagicMock(name="conn")

            def __exit__(self_inner, *exc):
                return False

        def fake_connect(args, *a, **kw):
            captured["connect_args"] = args
            captured["connect_kwargs"] = kw
            return _ConnCM()

        monkeypatch.setattr(dal_table.database, "connect", fake_connect)
        monkeypatch.setattr(dal_table.database, "cursor", lambda conn: MagicMock(name="cursor"))

        pool = MagicMock(name="pool")
        # Call get_table; we don't care about the return shape because
        # the cursor mock returns MagicMock.
        dal_table.get_table(MagicMock(name="args"), "yahtzee-bob", pool=pool)

        assert captured["connect_kwargs"].get("pool") is pool

    def test_get_table_no_pool_falls_back(self, monkeypatch):
        """When ``pool`` is None, the legacy ``database.connect(args)``
        shape is used (no pool= kwarg).
        """
        captured = {}

        class _ConnCM:
            def __enter__(self_inner):
                return MagicMock(name="conn")

            def __exit__(self_inner, *exc):
                return False

        def fake_connect(args, *a, **kw):
            captured["connect_kwargs"] = kw
            return _ConnCM()

        monkeypatch.setattr(dal_table.database, "connect", fake_connect)
        monkeypatch.setattr(dal_table.database, "cursor", lambda conn: MagicMock(name="cursor"))

        dal_table.get_table(MagicMock(name="args"), "yahtzee-bob")
        assert "pool" not in captured["connect_kwargs"], (
            f"legacy fallback leaked pool=: {captured['connect_kwargs']!r}"
        )
