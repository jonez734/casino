#!/usr/bin/env python3
# casino/tests/test_client_clock_display.py
# Phase 1c: the play clock is shown to the player. The server owns the deadline; the client shows
# seconds left from it, on the bottom bar's left side and in the table list's Clock column.
# Pure tests: no daemon, no terminal.

import types
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from casino.client import bottombar
from casino.client import casino_client as cc
from casino.client.clock_display import countdown_text, parse_deadline, seconds_left

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_countdown_counts_down_from_the_server_deadline():
    assert countdown_text((NOW + timedelta(seconds=17)).isoformat(), now=NOW) == "clock 17s"


@pytest.mark.unit
def test_no_running_clock_shows_nothing():
    assert countdown_text(None, now=NOW) == ""
    assert countdown_text("", now=NOW) == ""


@pytest.mark.unit
def test_a_passed_deadline_shows_zero_not_a_negative_number():
    assert countdown_text((NOW - timedelta(seconds=5)).isoformat(), now=NOW) == "clock 0s"


@pytest.mark.unit
def test_a_naive_timestamp_is_read_as_utc():
    assert parse_deadline("2026-01-01T12:00:10").tzinfo is not None
    assert seconds_left(parse_deadline("2026-01-01T12:00:10"), now=NOW) == 10


@pytest.mark.unit
def test_bottom_bar_shows_table_type_and_countdown_on_the_left():
    client = types.SimpleNamespace(current_table_moniker="bj-jam", current_table_game_type="blackjack",
                                   current_table_deadline=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat())
    bottombar.attach(lambda: client)
    try:
        text = bottombar._table_left()
    finally:
        bottombar.detach()
    assert text.startswith("table: bj-jam (blackjack)")
    assert "clock " in text


@pytest.mark.unit
def test_bottom_bar_without_a_clock_shows_table_and_type_only():
    client = types.SimpleNamespace(current_table_moniker="bj-jam", current_table_game_type="blackjack",
                                   current_table_deadline=None)
    bottombar.attach(lambda: client)
    try:
        assert bottombar._table_left() == "table: bj-jam (blackjack)"
    finally:
        bottombar.detach()


@pytest.mark.unit
def test_clock_cell_shows_the_live_countdown_when_a_round_is_open():
    t = {"action_deadline": (datetime.now(timezone.utc) + timedelta(seconds=20)).isoformat(),
         "turn_seconds": 30, "clock_penalty": "skip"}
    assert cc._clock_cell(t).startswith("clock ")


@pytest.mark.unit
def test_clock_cell_shows_turn_length_and_penalty_when_idle():
    assert cc._clock_cell({"turn_seconds": 30, "clock_penalty": "remove", "action_deadline": None}) == "30s remove"


@pytest.mark.unit
def test_clock_cell_is_a_dash_when_the_clock_is_off():
    assert cc._clock_cell({"turn_seconds": 0, "action_deadline": None}) == "-"


@pytest.mark.unit
def test_table_list_has_a_clock_column():
    import inspect
    src = inspect.getsource(cc.CasinoClient)
    assert '"Players", "Clock"' in src


@pytest.mark.unit
def test_server_table_list_carries_the_clock_fields():
    import inspect
    from casino.services import table as tmod
    src = inspect.getsource(tmod)
    assert '"turn_seconds"' in src and '"clock_penalty"' in src and '"action_deadline"' in src


@pytest.mark.unit
def test_bed_table_shape_carries_the_clock_fields():
    from pathlib import Path
    sql = (Path(__file__).resolve().parents[1] / "sql" / "casino_read_functions.sql").read_text()
    for field in ("'turn_seconds'", "'clock_penalty'", "'action_deadline'"):
        assert field in sql, field
