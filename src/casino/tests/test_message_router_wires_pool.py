"""Regression tests for MessageRouter -> handler -> service pool wiring.

Verifies the chain: ``MessageRouter.__init__`` resolves a pool
once via ``_resolve_pool(args)`` and threads it into every
service-handler constructor that owns a DB-touching service.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from casino.api.handler import (
    ChatServiceHandler,
    GameServiceHandler,
    MessageRouter,
    TableServiceHandler,
    YahtzeeServiceHandler,
    TictactoeServiceHandler,
)
from casino.tests._session_mock import make_sessions_mock


def _make_args(pool=None):
    args = MagicMock()
    args.pool = pool
    return args


class TestHandlersAcceptPool:
    """Every handler constructor that owns a DB-touching service
    must accept and forward ``pool=``.
    """

    @pytest.mark.parametrize("cls", [
        TableServiceHandler,
        GameServiceHandler,
        ChatServiceHandler,
    ])
    def test_handler_accepts_pool_kwarg(self, cls):
        sig = inspect.signature(cls.__init__)
        assert "pool" in sig.parameters, f"{cls.__name__} missing pool"
        assert sig.parameters["pool"].default is None

    def test_yahtzee_handler_accepts_pool(self):
        sig = inspect.signature(YahtzeeServiceHandler.__init__)
        assert "pool" in sig.parameters
        assert sig.parameters["pool"].default is None

    def test_tictactoe_handler_accepts_pool(self):
        sig = inspect.signature(TictactoeServiceHandler.__init__)
        assert "pool" in sig.parameters
        assert sig.parameters["pool"].default is None


class TestMessageRouterThreadsPool:
    def test_router_threads_resolved_pool_to_table_handler(self):
        args = _make_args(pool="POOL")
        sessions = make_sessions_mock()
        with patch("casino.api.handler._resolve_pool", return_value="RESOLVED"):
            router = MessageRouter(args, session_registry=sessions)
        assert router.table_service._pool == "RESOLVED"

    def test_router_threads_pool_to_yahtzee_service(self):
        args = _make_args(pool="POOL")
        sessions = make_sessions_mock()
        with patch("casino.api.handler._resolve_pool", return_value="RESOLVED"):
            router = MessageRouter(args, session_registry=sessions)
        # The yahtzee handler builds a YahtzeeService via its
        # constructor; if pool= is threaded correctly the inner
        # service has the same pool.
        inner = router.yahtzee_service_handler._service
        assert inner._pool == "RESOLVED"

    def test_router_threads_pool_to_tictactoe_service(self):
        args = _make_args(pool="POOL")
        sessions = make_sessions_mock()
        with patch("casino.api.handler._resolve_pool", return_value="RESOLVED"):
            router = MessageRouter(args, session_registry=sessions)
        inner = router.tictactoe_service_handler._service
        assert inner._pool == "RESOLVED"

    def test_router_threads_pool_to_bank_service_via_game_handler(self):
        """The BetServiceHandler constructs a GameService in the
        current code base; assert the pool reaches it.
        """
        args = _make_args(pool="POOL")
        sessions = make_sessions_mock()
        with patch("casino.api.handler._resolve_pool", return_value="RESOLVED"):
            router = MessageRouter(args, session_registry=sessions)
        assert router.bet_service.game_service._pool == "RESOLVED"
        assert router.game_service.game_service._pool == "RESOLVED"
        assert router.table_service.table_service._pool == "RESOLVED"
