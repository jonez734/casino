"""casino.map_cardtable_player: schema, DAL agreement, roles, one dealer.

The schema file is the source of truth. The DAL and lib.py must query the
same table and columns, and must not reference the removed
``__map_cardtable_player`` name. Role behavior is checked against a mocked
``async_query`` so no database is needed.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import casino.dal.aiosql.table as async_table  # noqa: E402

SRC = Path(__file__).resolve().parents[1]
SCHEMA = (SRC / "sql" / "map_cardtable_player.sql").read_text()
COLUMNS = {"cardtablemoniker", "playermoniker", "role", "joinedat"}


def test_schema_defines_the_table_and_columns_used_by_dal():
    assert "create table if not exists casino.map_cardtable_player" in SCHEMA
    for col in COLUMNS:
        assert re.search(rf'"{col}"', SCHEMA), f"schema missing column {col}"


def test_schema_role_check_and_one_dealer_index():
    assert "check (role in ('player', 'spectator', 'dealer'))" in SCHEMA
    assert "where role = 'dealer'" in SCHEMA


def test_no_stale_table_name_in_production_code():
    for path in SRC.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert "__map_cardtable_player" not in text, f"stale name in {path}"


def test_dal_queries_use_schema_columns_only():
    """Every statement against map_cardtable_player uses schema columns."""
    src = inspect.getsource(async_table)
    statements = re.findall(
        r'"([^"]*map_cardtable_player[^"]*)"|"""(.*?)"""',
        src,
        re.S,
    )
    seat_sql = [a or b for a, b in statements if "map_cardtable_player" in (a or b)]
    assert seat_sql, "no seat statements found"
    for sql in seat_sql:
        # A bare ``tablemoniker`` is the removed column. ``AS tablemoniker``
        # is an output alias and is allowed.
        stripped = re.sub(r"\bAS\s+tablemoniker\b", "", sql, flags=re.I)
        if re.search(r"\btablemoniker\b", stripped):
            raise AssertionError(f"stale column tablemoniker in: {sql!r}")


def test_add_player_rejects_unknown_role():
    with patch.object(async_table.database, "async_query", new=AsyncMock(return_value=[])):
        try:
            asyncio.run(async_table.add_player_to_table(object(), "jam", "alice", role="king"))
        except ValueError:
            return
    raise AssertionError("expected ValueError for unknown role")


def test_add_player_returns_false_when_already_seated():
    with patch.object(async_table.database, "async_query", new=AsyncMock(return_value=[])) as q:
        ok = asyncio.run(async_table.add_player_to_table(object(), "jam", "alice"))
    assert ok is False
    assert q.await_args.kwargs["role"] == "player"


def test_get_table_dealer_none_means_virtual_dealer():
    with patch.object(async_table.database, "async_query", new=AsyncMock(return_value=[])):
        assert asyncio.run(async_table.get_table_dealer(object(), "jam")) is None


def test_get_table_dealer_returns_member_seated_as_dealer():
    rows = [{"playermoniker": "dana"}]
    with patch.object(async_table.database, "async_query", new=AsyncMock(return_value=rows)):
        assert asyncio.run(async_table.get_table_dealer(object(), "jam")) == "dana"


def test_spectators_filtered_by_role():
    with patch.object(async_table.database, "async_query", new=AsyncMock(return_value=[])) as q:
        asyncio.run(async_table.get_table_spectators(object(), "jam"))
    assert "role = 'spectator'" in q.await_args.args[1]
