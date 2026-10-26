#!/usr/bin/env python3
# casino/tests/test_casino_sql_functions_db.py
# Database-level checks for the casino table functions: engine.casino_read, engine.casino_op, and
# engine.casino_table_shape. Each test runs in one transaction that is rolled back, so the test
# database is left as it was.
#
# Requires CASINO_TEST_DB (a database with the bed and casino installs applied). Skipped otherwise.
# Connects as CASINO_TEST_DBUSER, which must be a superuser or a zoid6 member that can execute the
# functions. Marked integration: excluded from the default run.

import hashlib
import json
import os

import pytest

pytestmark = pytest.mark.integration  # needs a test database with the casino installs

DB = os.environ.get("CASINO_TEST_DB", "")
SKIP = not DB
REASON = "CASINO_TEST_DB not set (needs a database with the bed and casino installs)"


def _conn():
    import psycopg

    return psycopg.connect(
        dbname=DB,
        host=os.environ.get("CASINO_TEST_DBHOST", "localhost"),
        port=int(os.environ.get("CASINO_TEST_DBPORT", "5432")),
        user=os.environ.get("CASINO_TEST_DBUSER", "postgres"),
        password=os.environ.get("CASINO_TEST_DBPASSWORD", "") or None,
        autocommit=False,
    )


def _digest(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


@pytest.fixture
def db():
    if SKIP:
        pytest.skip(REASON)
    conn = _conn()
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture(autouse=True)
def _no_leftovers(request):
    """Remove sq_* members and tables left by an interrupted run, before the test starts."""
    if SKIP:
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("delete from casino.map_cardtable_player where playermoniker like 'sq\\_%' or cardtablemoniker like 'sq-%'")
            cur.execute("delete from casino.__bank_table where table_moniker like 'sq-%'")
            cur.execute("delete from casino.__table where moniker like 'sq-%'")
            cur.execute("delete from engine.__bed_token where moniker like 'sq\\_%'")
            cur.execute("delete from engine.map_member_flag where moniker like 'sq\\_%'")
            cur.execute("delete from engine.__member where moniker like 'sq\\_%'")
        conn.commit()
    finally:
        conn.close()


def _member(cur, moniker, sysop=False):
    cur.execute(
        "insert into engine.__member (moniker, loginid, email, password, datecreated, createdbymoniker, ui, credits) "
        "values (%s, %s, %s, '$2b$12$abcdefghijklmnopqrstuuUjq7JgA3m7X0Yf0zq8qY4x5z0m6b1jS', now(), %s, '{term}', 0)",
        (moniker, moniker, f"{moniker}@test.invalid", moniker),
    )
    if sysop:
        cur.execute("insert into engine.map_member_flag (moniker, name, value) values (%s, 'sysop', true)", (moniker,))


def _token(cur, token, moniker):
    cur.execute(
        "insert into engine.__bed_token (token_hash, moniker, session_id, issued_at, expires_at, is_sysop, "
        "bed_instance_id, websocket_id, claims) values (%s, %s, %s, now(), now() + interval '1 hour', false, "
        "'test', %s, '{}'::jsonb)",
        (_digest(token), moniker, f"sess-{moniker}", f"ws-{moniker}"),
    )


def _call(cur, fn, token, op, args):
    cur.execute(f"select engine.{fn}(%s, %s, %s::jsonb)", (_digest(token), op, json.dumps(args)))
    return cur.fetchone()[0]


def test_list_hides_hidden_tables_from_a_regular_member(db):
    with db.cursor() as cur:
        _member(cur, "sq_owner")
        _member(cur, "sq_viewer")
        _token(cur, "tok-owner", "sq_owner")
        _token(cur, "tok-viewer", "sq_viewer")
        _call(cur, "casino_op", "tok-owner", "create", {"game_type": "blackjack", "moniker": "sq-open"})
        _call(cur, "casino_op", "tok-owner", "create", {"game_type": "blackjack", "moniker": "sq-hidden", "hidden": True})
        seen = {t["moniker"] for t in _call(cur, "casino_read", "tok-viewer", "list_tables", {})["tables"]}
    assert "sq-open" in seen
    assert "sq-hidden" not in seen


def test_list_shows_hidden_tables_to_a_sysop(db):
    with db.cursor() as cur:
        _member(cur, "sq_owner")
        _member(cur, "sq_sys", sysop=True)
        _token(cur, "tok-owner", "sq_owner")
        _token(cur, "tok-sys", "sq_sys")
        _call(cur, "casino_op", "tok-owner", "create", {"game_type": "blackjack", "moniker": "sq-hidden2", "hidden": True})
        seen = {t["moniker"] for t in _call(cur, "casino_read", "tok-sys", "list_tables", {})["tables"]}
    assert "sq-hidden2" in seen


def test_get_refuses_a_hidden_table_to_a_regular_member(db):
    with db.cursor() as cur:
        _member(cur, "sq_owner")
        _member(cur, "sq_viewer")
        _token(cur, "tok-owner", "sq_owner")
        _token(cur, "tok-viewer", "sq_viewer")
        _call(cur, "casino_op", "tok-owner", "create", {"game_type": "blackjack", "moniker": "sq-hidden3", "hidden": True})
        out = _call(cur, "casino_read", "tok-viewer", "get_table", {"moniker": "sq-hidden3"})
    assert out["table"] is None


def test_create_makes_the_bank_link_and_the_owner_account(db):
    with db.cursor() as cur:
        _member(cur, "sq_owner")
        _token(cur, "tok-owner", "sq_owner")
        out = _call(cur, "casino_op", "tok-owner", "create", {"game_type": "blackjack", "moniker": "sq-bank"})
        assert out["success"] is True
        cur.execute("select count(*) from casino.__bank_table where table_moniker = 'sq-bank'")
        assert cur.fetchone()[0] == 1
        cur.execute("select count(*) from bank.__account where moniker = 'sq_owner'")
        assert cur.fetchone()[0] == 1


def test_non_owner_cannot_update_and_the_refusal_names_the_op(db):
    with db.cursor() as cur:
        _member(cur, "sq_owner")
        _member(cur, "sq_other")
        _token(cur, "tok-owner", "sq_owner")
        _token(cur, "tok-other", "sq_other")
        _call(cur, "casino_op", "tok-owner", "create", {"game_type": "blackjack", "moniker": "sq-upd"})
    # The refusal aborts the transaction, so run it in a savepoint and roll back to it.
    with db.cursor() as cur:
        cur.execute("savepoint refused")
        with pytest.raises(Exception) as exc:
            _call(cur, "casino_op", "tok-other", "update", {"moniker": "sq-upd", "status": "closed"})
        assert "casino_op(update): forbidden" in str(exc.value)
        cur.execute("rollback to savepoint refused")


def test_update_rejects_a_bad_status_with_a_message(db):
    with db.cursor() as cur:
        _member(cur, "sq_owner")
        _token(cur, "tok-owner", "sq_owner")
        _call(cur, "casino_op", "tok-owner", "create", {"game_type": "blackjack", "moniker": "sq-status"})
        out = _call(cur, "casino_op", "tok-owner", "update", {"moniker": "sq-status", "status": "bogus"})
    assert out["success"] is False
    assert "open or closed" in out["message"]


def test_join_then_leave_changes_the_seat(db):
    with db.cursor() as cur:
        _member(cur, "sq_owner")
        _member(cur, "sq_guest")
        _token(cur, "tok-owner", "sq_owner")
        _token(cur, "tok-guest", "sq_guest")
        _call(cur, "casino_op", "tok-owner", "create", {"game_type": "blackjack", "moniker": "sq-seat"})
        _call(cur, "casino_op", "tok-guest", "join", {"moniker": "sq-seat"})
        cur.execute("select count(*) from casino.map_cardtable_player where cardtablemoniker='sq-seat' and playermoniker='sq_guest'")
        assert cur.fetchone()[0] == 1
        _call(cur, "casino_op", "tok-guest", "leave", {"moniker": "sq-seat"})
        cur.execute("select count(*) from casino.map_cardtable_player where cardtablemoniker='sq-seat' and playermoniker='sq_guest'")
        assert cur.fetchone()[0] == 0


def test_table_shape_lists_seated_players_and_spectators(db):
    with db.cursor() as cur:
        _member(cur, "sq_owner")
        _token(cur, "tok-owner", "sq_owner")
        _call(cur, "casino_op", "tok-owner", "create", {"game_type": "blackjack", "moniker": "sq-shape"})
        _call(cur, "casino_op", "tok-owner", "join", {"moniker": "sq-shape"})
        cur.execute("select engine.casino_table_shape(t) from casino.__table t where moniker='sq-shape'")
        shape = cur.fetchone()[0]
    assert shape["moniker"] == "sq-shape"
    assert shape["game_type"] == "blackjack"
    assert "sq_owner" in shape["players"]
    assert "spectators" in shape


def test_unknown_op_is_refused_with_its_name(db):
    with db.cursor() as cur:
        _member(cur, "sq_owner")
        _token(cur, "tok-owner", "sq_owner")
        with pytest.raises(Exception) as exc:
            _call(cur, "casino_read", "tok-owner", "bogus", {})
    assert "unknown op bogus" in str(exc.value)


def test_no_live_session_is_refused_with_the_op(db):
    with db.cursor() as cur:
        with pytest.raises(Exception) as exc:
            _call(cur, "casino_read", "no-such-token", "list_tables", {})
    assert "casino_read(list_tables): no live session" in str(exc.value)
