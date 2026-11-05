#!/usr/bin/env python3
"""Check what a slot spin does on a retry, and that money is never moved twice.

Runs against a real database, through the same settlement function the slot service calls
(engine.casino_settle_spin). It creates its own scratch member and token, runs each case,
reports PASS or FAIL for each, and removes everything it created.

Cases:
  1. one spin settles once: the balance moves by net, one transaction and one spin row.
  2. a retry with the same correlation id does not settle again.
  3. two different spins both settle (a dedupe must not block normal play).
  4. a settle that committed but whose caller saw an error, then retried, moves money once.
  5. a refused spin (insufficient funds) moves no money and writes no spin row.

Usage:
  scripts/check-spin-retry.py --db zoid6test            # read-write: the test database only
  scripts/check-spin-retry.py --db zoid6test --keep     # leave the scratch rows for inspection

Exit status is 0 when every case passes, 1 when any case fails, 2 on setup errors.

Only run this against a test database. It inserts and deletes scratch members, bank accounts,
transactions, spins, and bearer tokens.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from dataclasses import dataclass

REPO_SRC = [
    "/home/opencode/data/work/casino/src",
    "/home/opencode/data/work/bed/src",
    "/home/opencode/data/work/bbsengine6/py/src",
]
for p in REPO_SRC:
    if p not in sys.path:
        sys.path.insert(0, p)


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def _setup(db: str):
    import argparse as _ap

    from bbsengine6 import database
    from bed.store.token_store import token_hash

    args = _ap.Namespace(databasename=db, debug=False, database=db)
    return args, database, token_hash


def _mint_token(args, moniker: str) -> str:
    """Write a live bearer token row for ``moniker``, the way bed does at login."""
    from bed.api.token_store import DBTokenStore, TokenRecord
    from casino.api._auth import _TOKEN_CLAIM_VERSION, encode_token

    secret = b"spin-retry-check-secret-32-bytes!!"
    now = time.time()
    session_id = f"retry-{uuid.uuid4().hex[:8]}"
    claims = {
        "version": _TOKEN_CLAIM_VERSION, "moniker": moniker, "issued_at": now,
        "expires_at": now + 3600, "session_id": session_id, "is_sysop": False,
        "bed_instance_id": "retry-check", "websocket_id": "ws-retry", "loginid": moniker,
    }
    token = encode_token(claims, secret)
    DBTokenStore(args).put(TokenRecord(
        token=token, moniker=moniker, session_id=session_id, issued_at=now,
        expires_at=now + 3600, is_sysop=False, bed_instance_id="retry-check",
        websocket_id="ws-retry", claims=claims, loginid=moniker,
    ))
    return token


def _create_member(database, args, moniker: str, balance: int) -> None:
    with database.connect(args) as conn, database.cursor(conn) as cur:
        # the spin's audit row has a foreign key to the member table
        cur.execute(
            "INSERT INTO engine.__member (moniker, email, approved) VALUES (%s, %s, true) "
            "ON CONFLICT (moniker) DO NOTHING",
            (moniker, f"{moniker}@retry-check.local"),
        )
        cur.execute(
            "INSERT INTO bank.__account (moniker, balance, maxtransfer, overdraft_limit) "
            "VALUES (%s, %s, 1000000, 0) ON CONFLICT (moniker) DO NOTHING",
            (moniker, balance),
        )
        cur.execute(
            "INSERT INTO casino.__player (moniker) VALUES (%s) ON CONFLICT DO NOTHING",
            (moniker,),
        )
        conn.commit()


def _create_table(database, args, table: str) -> None:
    """A scratch slots table row: the spin's audit row has a foreign key to it."""
    with database.connect(args) as conn, database.cursor(conn) as cur:
        cur.execute(
            "INSERT INTO casino.__table (moniker, type) VALUES (%s, 'slots') ON CONFLICT DO NOTHING",
            (table,),
        )
        conn.commit()


def _balance(database, args, moniker: str) -> int:
    with database.connect(args) as conn, database.cursor(conn) as cur:
        cur.execute("SELECT balance FROM bank.__account WHERE moniker = %s", (moniker,))
        row = cur.fetchone()
        return int(row["balance"]) if row else 0


def _counts(database, args, moniker: str, table: str) -> tuple[int, int]:
    """(bank transactions, slot spin rows) for ``moniker`` at ``table``."""
    with database.connect(args) as conn, database.cursor(conn) as cur:
        cur.execute(
            "SELECT count(*) AS n FROM bank.__transaction t "
            "JOIN bank.__account a ON a.id = t.accountid "
            "WHERE a.moniker = %s AND t.description LIKE %s",
            (moniker, f"%at {table}%"),
        )
        txns = int(cur.fetchone()["n"])
        cur.execute(
            "SELECT count(*) AS n FROM casino.__slot_spin WHERE player_moniker = %s AND table_moniker = %s",
            (moniker, table),
        )
        spins = int(cur.fetchone()["n"])
    return txns, spins


def _settle(database, args, token_hash, token: str, payload: dict):
    """Call the settlement function exactly as the slot service does. Returns the jsonb result."""
    with database.connect(args) as conn, database.cursor(conn) as cur:
        cur.execute(
            "SELECT engine.casino_settle_spin(%s, %s::jsonb)",
            (token_hash(token), database.Jsonb(payload)),
        )
        row = cur.fetchone()
        conn.commit()
    value = row["casino_settle_spin"] if isinstance(row, dict) else row[0]
    return value


def _payload(table: str, bet: int, payout: int, corr: str) -> dict:
    return {
        "table_moniker": table, "bet": bet, "payout": payout, "net": payout - bet,
        "reels": [], "wins": [], "correlation_id": corr,
    }


def _cleanup(database, args, moniker: str, table: str, tokens: list[str]) -> None:
    from bed.api.token_store import DBTokenStore

    store = DBTokenStore(args)
    for t in tokens:
        store.delete(t)
    with database.connect(args) as conn, database.cursor(conn) as cur:
        cur.execute("DELETE FROM casino.__slot_spin WHERE player_moniker = %s", (moniker,))
        cur.execute("DELETE FROM bank.__transaction WHERE membermoniker = %s", (moniker,))
        cur.execute("DELETE FROM bank.__account WHERE moniker = %s", (moniker,))
        cur.execute("DELETE FROM casino.__player WHERE moniker = %s", (moniker,))
        cur.execute("DELETE FROM casino.__table WHERE moniker = %s", (table,))
        cur.execute("DELETE FROM engine.__member WHERE moniker = %s", (moniker,))
        conn.commit()


def run(db: str, keep: bool) -> list[Result]:
    args, database, token_hash = _setup(db)
    suffix = uuid.uuid4().hex[:8]
    moniker = f"retrychk_{suffix}"
    table = f"retrychk_tbl_{suffix}"
    tokens: list[str] = []
    results: list[Result] = []

    try:
        _create_table(database, args, table)
        _create_member(database, args, moniker, balance=1000)
        token = _mint_token(args, moniker)
        tokens.append(token)
        start = _balance(database, args, moniker)

        # 1. one spin settles once
        corr = uuid.uuid4().hex
        r = _settle(database, args, token_hash, token, _payload(table, 10, 0, corr))
        after = _balance(database, args, moniker)
        txns, spins = _counts(database, args, moniker, table)
        ok = bool(r.get("success")) and after == start - 10 and txns == 1 and spins == 1
        results.append(Result("1 one spin settles once", ok,
                              f"success={r.get('success')} balance {start}->{after} txns={txns} spins={spins}"))

        # 2. a retry with the same correlation id must not settle again
        r2 = _settle(database, args, token_hash, token, _payload(table, 10, 0, corr))
        after2 = _balance(database, args, moniker)
        txns2, spins2 = _counts(database, args, moniker, table)
        dup_blocked = (after2 == after) and (txns2 == txns) and (spins2 == spins)
        results.append(Result(
            "2 same correlation id retried is not settled twice", dup_blocked,
            f"retry success={r2.get('success')} code={r2.get('code')} balance {after}->{after2} "
            f"txns {txns}->{txns2} spins {spins}->{spins2}"))

        # 3. two different spins both settle
        before3 = _balance(database, args, moniker)
        _settle(database, args, token_hash, token, _payload(table, 10, 0, uuid.uuid4().hex))
        _settle(database, args, token_hash, token, _payload(table, 10, 0, uuid.uuid4().hex))
        after3 = _balance(database, args, moniker)
        results.append(Result("3 distinct spins both settle", after3 == before3 - 20,
                              f"balance {before3}->{after3} (expect -20)"))

        # 4. settle committed, caller saw an error, then retried with the same payload
        before4 = _balance(database, args, moniker)
        corr4 = uuid.uuid4().hex
        _settle(database, args, token_hash, token, _payload(table, 5, 0, corr4))  # committed
        # the caller (slot service) would have raised after this point and reported service_error
        _settle(database, args, token_hash, token, _payload(table, 5, 0, corr4))  # client retry
        after4 = _balance(database, args, moniker)
        results.append(Result("4 committed-then-retried spin moves money once", after4 == before4 - 5,
                              f"balance {before4}->{after4} (expect -5)"))

        # 5. a refused spin moves nothing and writes no spin row
        poor = f"retrychk_poor_{suffix}"
        _create_member(database, args, poor, balance=0)
        poor_token = _mint_token(args, poor)
        tokens.append(poor_token)
        txn_before, spin_before = _counts(database, args, poor, table)
        r5 = _settle(database, args, token_hash, poor_token, _payload(table, 10, 0, uuid.uuid4().hex))
        txn_after, spin_after = _counts(database, args, poor, table)
        results.append(Result(
            "5 refused spin moves no money", (not r5.get("success")) and txn_after == txn_before
            and spin_after == spin_before and _balance(database, args, poor) == 0,
            f"code={r5.get('code')} txns {txn_before}->{txn_after} spins {spin_before}->{spin_after}"))
        if not keep:
            _cleanup(database, args, poor, table, [])
    finally:
        if not keep:
            _cleanup(database, args, moniker, table, tokens)
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="test database name (never a production database)")
    ap.add_argument("--keep", action="store_true", help="leave the scratch rows in place")
    opts = ap.parse_args()

    try:
        results = run(opts.db, opts.keep)
    except Exception as exc:  # setup or connection failure
        print(f"setup error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    failed = 0
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        failed += 0 if r.ok else 1
        print(f"{status}  {r.name}\n      {r.detail}")
    print(f"\n{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
