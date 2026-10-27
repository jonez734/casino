#!/usr/bin/env python3
# casino/tests/test_join_seat_capacity.py
# Phase 4 slice 2: join_table refuses a player when the table has no free seat, using the
# seat-module registry. Stubbed: no database.

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.dal import table as dal_table
from casino.services import table as table_mod


def _service():
    svc = table_mod.TableService.__new__(table_mod.TableService)
    svc.args = SimpleNamespace()
    svc._pool = None
    return svc


def _join(game_type, seated):
    svc = _service()
    table = {"moniker": "t1", "type": game_type}
    with patch.object(dal_table, "get_table", return_value=table), \
         patch.object(dal_table, "count_seated", return_value=seated), \
         patch.object(dal_table, "add_player_to_table", return_value=True) as add, \
         patch.object(table_mod, "tablegroups", create=True):
        result = svc.join_table("t1", "newcomer", is_sysop=False)
    return result, add


@pytest.mark.unit
def test_join_is_refused_when_a_blackjack_table_is_full():
    result, add = _join("blackjack", seated=7)
    assert result["success"] is False
    assert "full" in result["message"].lower()
    add.assert_not_called()


@pytest.mark.unit
def test_join_is_allowed_when_a_blackjack_table_has_room():
    result, add = _join("blackjack", seated=6)
    assert result["success"] is True
    add.assert_called_once()


@pytest.mark.unit
def test_slots_join_is_refused_once_the_single_seat_is_taken():
    result, add = _join("slots", seated=1)
    assert result["success"] is False
    add.assert_not_called()


@pytest.mark.unit
def test_join_for_a_game_without_a_seat_rule_is_not_refused_on_capacity():
    result, _ = _join("craps", seated=99)
    assert result["success"] is True


@pytest.mark.unit
def test_count_seated_is_a_dal_function():
    assert callable(getattr(dal_table, "count_seated", None))
