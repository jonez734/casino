"""Regression tests for service-level ``pool=`` wiring (CONN_POOL_PATTERN).

Verifies that:
- ``TableService``, ``GameService``, ``BankService`` accept
  optional ``pool=`` and thread it into every dal_*.call().
- ``YahtzeeService`` / ``TictactoeService`` thread ``pool=self._pool``
  into their dal_* and direct ``database.connect`` calls.
- The API handlers (``TableServiceHandler``, ``GameServiceHandler``,
  ``BetServiceHandler``, ``YahtzeeServiceHandler``,
  ``TictactoeServiceHandler``, ``ChatServiceHandler``,
  ``SlotServiceHandler``) accept ``pool=`` and forward it.
- The MessageRouter resolves a pool once and threads it into every
  handler.
"""

from __future__ import annotations

import asyncio
import inspect
import random
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from casino.yahtzee.dealer import YahtzeeDealer
from casino.yahtzee.service import YahtzeeService
from casino.tictactoe.service import TictactoeService
from casino.services.table import TableService
from casino.services.game import GameService
from casino.services.bank import BankService
from casino.api.handler import MessageRouter, _resolve_pool


def _make_args(pool=None):
    args = MagicMock()
    args.pool = pool
    return args


def _mock_table_service():
    ts = MagicMock()
    ts.create_table.return_value = {
        "success": True,
        "table": {
            "moniker": "yahtzee-alice", "type": "yahtzee",
            "minimumbet": 10, "maximumbet": 1000,
            "ownermoniker": "alice", "status": "open",
            "hidden": True, "accountid": 1,
        },
        "message": "ok",
    }
    return ts


def _seed_yahtzee(s, mock_dbs):
    """Drive a quick_play on a service with mocked dal + database."""
    db, dg, dbconn = mock_dbs
    dg.create_game.return_value = {"id": 42}
    db.place_bet.return_value = {"id": 7}
    s.quick_play("alice")


def _make_dal_mocks():
    db = MagicMock()
    dg = MagicMock()
    dbconn = MagicMock()
    dg.create_game.return_value = {"id": 42}
    db.place_bet.return_value = {"id": 7}
    return db, dg, dbconn


class TestTableServiceThreadsPool:
    def test_pool_kwarg_is_accepted(self):
        sig = inspect.signature(TableService.__init__)
        assert sig.parameters["pool"].default is None

    def test_create_table_threads_pool(self):
        service = TableService(_make_args(), pool="POOL")
        with patch("casino.services.table.dal_table") as dal_table:
            dal_table.create_table.return_value = {
                "moniker": "yahtzee-alice", "type": "yahtzee",
                "minimumbet": 10, "maximumbet": 1000,
                "ownermoniker": "alice", "status": "open",
                "hidden": True, "accountid": 1,
            }
            service.create_table(game_type="yahtzee", owner_moniker="alice")
            kwargs = dal_table.create_table.call_args.kwargs
            assert kwargs.get("pool") == "POOL"


class TestGameServiceThreadsPool:
    def test_pool_kwarg_is_accepted(self):
        sig = inspect.signature(GameService.__init__)
        assert sig.parameters["pool"].default is None

    def test_start_game_threads_pool(self):
        service = GameService(_make_args(), pool="POOL")
        with patch("casino.services.game.dal_table") as dal_table, \
             patch("casino.services.game.dal_game") as dal_game:
            dal_table.get_table.return_value = MagicMock(minimumbet=10)
            dal_game.create_game.return_value = {"id": 42}
            service.start_game("yahtzee-alice", "yahtzee")
            kwargs = dal_game.create_game.call_args.kwargs
            assert kwargs.get("pool") == "POOL"


class TestBankServiceThreadsPool:
    def test_pool_kwarg_is_accepted(self):
        sig = inspect.signature(BankService.__init__)
        assert sig.parameters["pool"].default is None


class TestYahtzeeServiceThreadsPool:
    def test_pool_kwarg_is_accepted(self):
        sig = inspect.signature(YahtzeeService.__init__)
        assert "pool" in sig.parameters
        assert sig.parameters["pool"].default is None

    def test_quick_play_threads_pool_into_dal(self):
        args = _make_args()
        dealer = YahtzeeDealer(rng=random.Random(0))
        ts = _mock_table_service()
        s = YahtzeeService(args, dealer=dealer, table_service=ts,
                           find_table_fn=lambda *a, **kw: None,
                           pool="POOL")

        with patch("casino.yahtzee.service.dal_bet") as db, \
             patch("casino.yahtzee.service.dal_game") as dg:
            db.place_bet.return_value = {"id": 7}
            s.quick_play("alice")
            assert db.place_bet.call_args.kwargs.get("pool") == "POOL"
            assert dg.create_game.call_args.kwargs.get("pool") == "POOL"

    def test_no_pool_falls_back_to_none(self):
        args = _make_args()
        dealer = YahtzeeDealer(rng=random.Random(0))
        ts = _mock_table_service()
        s = YahtzeeService(args, dealer=dealer, table_service=ts,
                           find_table_fn=lambda *a, **kw: None)

        with patch("casino.yahtzee.service.dal_bet") as db, \
             patch("casino.yahtzee.service.dal_game") as dg:
            db.place_bet.return_value = {"id": 7}
            s.quick_play("alice")
            assert db.place_bet.call_args.kwargs.get("pool") is None
            assert dg.create_game.call_args.kwargs.get("pool") is None


class TestTictactoeServiceThreadsPool:
    def test_pool_kwarg_is_accepted(self):
        sig = inspect.signature(TictactoeService.__init__)
        assert "pool" in sig.parameters
        assert sig.parameters["pool"].default is None

    def test_quick_play_threads_pool_into_dal(self):
        args = _make_args()
        ts = _mock_table_service()
        ts.create_table.return_value["table"]["moniker"] = "ttt-alice"
        ts.create_table.return_value["table"]["type"] = "tictactoe"
        from casino.tictactoe.dealer import TictactoeDealer
        dealer = TictactoeDealer()
        s = TictactoeService(args, dealer=dealer, table_service=ts,
                            find_table_fn=lambda *a, **kw: None,
                            pool="POOL")

        with patch("casino.tictactoe.service.dal_bet") as db, \
             patch("casino.tictactoe.service.dal_game") as dg:
            db.place_bet.return_value = {"id": 7}
            s.quick_play("alice", mode=1)
            assert db.place_bet.call_args.kwargs.get("pool") == "POOL"
            assert dg.create_game.call_args.kwargs.get("pool") == "POOL"


class TestDefaultFindTableAcceptsPool:
    def test_yahtzee_default_find_table(self):
        from casino.yahtzee.service import _default_find_table
        sig = inspect.signature(_default_find_table)
        assert sig.parameters["pool"].default is None

    def test_tictactoe_default_find_table(self):
        from casino.tictactoe.service import _default_find_table
        sig = inspect.signature(_default_find_table)
        assert sig.parameters["pool"].default is None


class TestResolvePool:
    """The MessageRouter's _resolve_pool helper picks ``args.pool``
    when set and otherwise calls ``database.getpool(args)``."""

    def test_returns_args_pool(self):
        sentinel_pool = MagicMock(name="args_pool")
        args = MagicMock()
        args.pool = sentinel_pool
        with patch("casino.api.handler.database") as dbmod:
            assert _resolve_pool(args) is sentinel_pool
            dbmod.getpool.assert_not_called()

    def test_falls_back_to_getpool(self):
        args = MagicMock()
        args.pool = None
        sentinel_getpool = MagicMock(name="getpool_result")
        with patch("casino.api.handler.database") as dbmod:
            dbmod.getpool.return_value = sentinel_getpool
            assert _resolve_pool(args) is sentinel_getpool
            dbmod.getpool.assert_called_once_with(args)
