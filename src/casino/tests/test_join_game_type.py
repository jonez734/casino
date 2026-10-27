#!/usr/bin/env python3
# casino/tests/test_join_game_type.py
# Phase 3: the join reply carries the table's game type, so the client knows what it sat down at
# without a second request. Stubbed: no database.

import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.api import handler as handler_mod
from casino.client import casino_client as cc
from casino.dal import table as dal_table
from casino.services import table as table_mod


def _service():
    svc = table_mod.TableService.__new__(table_mod.TableService)
    svc.args = SimpleNamespace()
    svc._pool = None
    return svc


@pytest.mark.unit
def test_join_table_result_includes_the_game_type():
    svc = _service()
    table = {"moniker": "tictactoe-x", "type": "tictactoe"}
    with patch.object(dal_table, "get_table", return_value=table), \
         patch.object(dal_table, "add_player_to_table", return_value=True), \
         patch.object(table_mod, "tablegroups", create=True):
        result = svc.join_table("tictactoe-x", "player", is_sysop=False)
    assert result["success"] is True
    assert result["game_type"] == "tictactoe"


@pytest.mark.unit
def test_join_reply_carries_game_type_from_the_service_result():
    src = inspect.getsource(handler_mod)
    # The joined_table reply is built from the service result and includes game_type.
    assert '"game_type": result.get("game_type")' in src or '"game_type": result["game_type"]' in src


@pytest.mark.unit
def test_client_sets_current_table_game_type_from_the_join_reply():
    src = inspect.getsource(cc.CasinoClient.handle_message)
    branch = src[src.index('elif msg_type == "joined_table":'):]
    branch = branch[:branch.index("elif", 20)] if "elif" in branch[20:] else branch
    assert "current_table_game_type" in branch
    assert 'msg.get("game_type")' in branch
