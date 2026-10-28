# casino/tests/test_lobby_no_direct_table_reads.py
# Regression pin: the casino server's lobby (list_tables) must not read casino.__table directly.
# bed holds no table privileges on casino tables; database listings go through bed's
# casino_list_tables -> engine.casino_read. The server lists only the in-memory poker tables.

from __future__ import annotations

import argparse
from unittest.mock import MagicMock

from casino.api.handler import TableServiceHandler
from casino.poker.api_handler import PokerServiceHandler
from casino.services.poker import PokerService


def _ws():
    ws = MagicMock()
    ws.id = 1
    return ws


def test_lobby_does_not_call_db_table_listing():
    """A lobby request must never call the DB table listing, for any filter."""
    sessions = MagicMock()
    state = MagicMock(moniker="alice", is_sysop=True, table_moniker=None)
    table_service = MagicMock()

    handler = TableServiceHandler.__new__(TableServiceHandler)
    handler.table_service = table_service
    handler.poker_service_handler = None
    handler._check_access = MagicMock(return_value=(state, None))

    import asyncio

    for game_type in (None, "", "blackjack", "tictactoe", "poker"):
        msg = {"type": "list_tables"} if game_type is None else {"type": "list_tables", "game_type": game_type}
        out = asyncio.run(handler._handle_list_tables(_ws(), msg))
        assert out["type"] == "table_list"
    table_service.list_tables.assert_not_called()


def test_lobby_lists_poker_tables_only():
    """With a poker handler wired, the lobby returns poker tables and no DB rows."""
    svc = PokerService(argparse.Namespace(databasename="zoid6test", debug=False))
    svc.create_table(
        table_moniker="lobby-pin",
        variant_name="holdem",
        betting_structure="no_limit",
        small_blind=1,
        big_blind=2,
    )
    poker = PokerServiceHandler(argparse.Namespace(), None, service=svc)

    table_service = MagicMock()
    state = MagicMock(moniker="alice", is_sysop=False, table_moniker=None)

    handler = TableServiceHandler.__new__(TableServiceHandler)
    handler.table_service = table_service
    handler.poker_service_handler = poker
    handler._check_access = MagicMock(return_value=(state, None))

    import asyncio

    out = asyncio.run(handler._handle_list_tables(_ws(), {"type": "list_tables", "game_type": "poker"}))
    monikers = [t["moniker"] for t in out["tables"]]
    assert "lobby-pin" in monikers
    assert all(t["type"] == "poker" for t in out["tables"])
    table_service.list_tables.assert_not_called()

    blackjack = asyncio.run(handler._handle_list_tables(_ws(), {"type": "list_tables", "game_type": "blackjack"}))
    assert blackjack["tables"] == []
    table_service.list_tables.assert_not_called()
