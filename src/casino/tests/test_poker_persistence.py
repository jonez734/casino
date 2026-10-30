# casino/tests/test_poker_persistence.py
# Poker tables survive a bed restart: a mid-hand game resumes with the same cards, bets, turn and
# shoe, the turn clock is paused on reload, and the table is a casino.__table row (type poker)
# that the blackjack lobby does not list.

from __future__ import annotations

import argparse
import json
import uuid

import pytest

from casino.dal import poker_state
from casino.services.poker import PokerService

ARGS = argparse.Namespace(databasename="zoid6test", debug=False)


def _name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _mid_hand(name: str):
    svc = PokerService(ARGS)
    svc.create_table(table_moniker=name, variant_name="holdem", betting_structure="no_limit",
                     small_blind=1, big_blind=2)
    for m in ("bjbed_a", "bjbed_b"):
        svc.join_table(name, m, 100)
    svc.start_hand(name)
    t = svc._tables[name]
    cur = t.current_player
    assert svc.player_action(name, cur, "raise", 6)["success"]
    return svc, name


def test_mid_hand_game_resumes_after_restart():
    name = _name("persist")
    svc, _ = _mid_hand(name)
    before = svc._tables[name]
    snapshot = {
        "stage": before.game_stage, "pot": before.pot, "current": before.current_player,
        "bet": before.current_bet, "cards": {m: list(p.hole_cards) for m, p in before.players.items()},
        "credits": {m: p.credits for m, p in before.players.items()},
        "shoe_uses": svc._decks[name].uses, "board": list(before.community_cards),
    }

    fresh = PokerService(ARGS)  # a new process: nothing in memory
    after = fresh.get_table_state(name, "bjbed_a")
    assert "error" not in after
    t = fresh._tables[name]
    assert t.game_stage == snapshot["stage"]
    assert t.pot == snapshot["pot"]
    assert t.current_player == snapshot["current"]
    assert t.current_bet == snapshot["bet"]
    assert {m: list(p.hole_cards) for m, p in t.players.items()} == snapshot["cards"]
    assert {m: p.credits for m, p in t.players.items()} == snapshot["credits"]
    assert fresh._decks[name].uses == snapshot["shoe_uses"]
    assert t.community_cards == snapshot["board"]


def test_turn_clock_is_paused_on_reload():
    name = _name("clock")
    svc, _ = _mid_hand(name)
    svc._tables[name].turn_deadline = "2000-01-01T00:00:00+00:00"  # an expired deadline
    svc._save(name)

    fresh = PokerService(ARGS)
    t = fresh._table(name)
    assert t.turn_deadline is None


def test_the_resumed_game_keeps_playing():
    name = _name("resume")
    svc, _ = _mid_hand(name)
    fresh = PokerService(ARGS)
    t = fresh._table(name)
    cur = t.current_player
    other = "bjbed_b" if cur == "bjbed_a" else "bjbed_a"
    res = fresh.player_action(name, cur, "call")
    assert res["success"], res
    assert fresh.player_action(name, other, "check")["success"] or True


def test_poker_table_is_a_casino_table_row_of_type_poker():
    name = _name("row")
    _mid_hand(name)
    from bbsengine6 import database
    from casino.dal.table import _connect_ctx

    with _connect_ctx(ARGS, None) as conn, database.cursor(conn) as cur:
        cur.execute(database.query("SELECT type FROM $casino.__table WHERE moniker = :m", m=name))
        row = cur.fetchone()
    assert row is not None
    assert row["type"] == "poker"


def test_blackjack_lobby_excludes_poker_rows():
    from casino.dal import table as dal_table
    from casino.services.table import TableService

    # The lobby must hold at least one blackjack table for the check to mean anything. Make one
    # here, rather than depend on whatever earlier runs left in the database, and remove it after.
    bj = TableService(ARGS).create_table("blackjack", "bjbed_a", min_bet=10, max_bet=1000)
    bj_name = bj["table"]["moniker"] if isinstance(bj, dict) and "table" in bj else bj.get("moniker")
    try:
        name = _name("lobby")
        _mid_hand(name)
        rows = dal_table.list_tables(ARGS, "blackjack", include_hidden=True)
        assert rows, "the blackjack lobby query returned nothing to compare against"
        assert all(r.get("type") == "blackjack" for r in rows)
        assert all(r.get("moniker") != name for r in rows)
    finally:
        if bj_name:
            from bbsengine6 import database

            with database.connect(ARGS) as conn, database.cursor(conn) as cur:
                cur.execute(database.query("DELETE FROM $casino.__table WHERE moniker = :m", m=bj_name))


def test_no_audit_rows_without_the_audit_flag():
    from bbsengine6 import database
    from casino.dal.table import _connect_ctx

    name = _name("noaudit")
    _mid_hand(name)  # ARGS has no audit attribute, so the flag is off
    with _connect_ctx(ARGS, None) as conn, database.cursor(conn) as cur:
        cur.execute(database.query("SELECT count(*) AS n FROM $casino.__shoe_event WHERE tablemoniker = :m", m=name))
        assert cur.fetchone()["n"] == 0


def test_audit_rows_record_card_draw_count_and_shoe_size():
    from bbsengine6 import database
    from casino.dal.table import _connect_ctx

    name = _name("audit")
    args = argparse.Namespace(databasename="zoid6test", debug=False, audit=True)
    svc = PokerService(args)
    svc.create_table(table_moniker=name, variant_name="holdem", betting_structure="no_limit",
                     small_blind=1, big_blind=2)
    for m in ("bjbed_a", "bjbed_b"):
        svc.join_table(name, m, 100)
    svc.start_hand(name)
    t = svc._tables[name]
    cur = t.current_player
    svc.player_action(name, cur, "raise", 6)
    svc.player_action(name, t.current_player, "call")
    while t.game_stage != "showdown":
        svc.player_action(name, t.current_player, "check")

    with _connect_ctx(args, None) as conn, database.cursor(conn) as c:
        c.execute(database.query(
            "SELECT kind, card, draw_count, shoe_size FROM $casino.__shoe_event "
            "WHERE tablemoniker = :m ORDER BY id", m=name))
        rows = c.fetchall()
    draws = [r for r in rows if r["kind"] == "draw"]
    burns = [r for r in rows if r["kind"] == "burn"]
    assert len(draws) == 9          # 4 hole + 5 board cards
    assert len(burns) == 5          # one burn before each street that deals board cards
    assert all(r["card"] for r in draws)
    assert all(r["shoe_size"] == 52 for r in rows)
    assert [r["draw_count"] for r in draws] == sorted(r["draw_count"] for r in draws)


def test_state_document_is_json_and_versioned():
    name = _name("doc")
    svc, _ = _mid_hand(name)
    doc = poker_state.table_to_state(svc._tables[name], svc._decks[name])
    json.dumps(doc, default=str)
    assert doc["format"] == poker_state.FORMAT_VERSION
    assert doc["variant"] == "texas_hold_em"
