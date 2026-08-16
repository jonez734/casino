# casino/dal/slots.py
# Slot spin history and paytable config DAL.

from __future__ import annotations

from typing import Any

from bbsengine6 import database
from bbsengine6.database import Jsonb


def _coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    """Cast psycopg-native types to JSON-safe values.

    - NUMERIC columns (``bet``, ``payout``) come back as
      :class:`decimal.Decimal`; ``json.dumps`` cannot serialize them.
      The DB stores them as integer cents-equivalents so a cast is safe.
    - Timestamp columns (``spun_at``) come back as
      :class:`datetime.datetime`; stringify as ISO-8601 so the wire
      envelope stays JSON-clean.
    """
    out = dict(row)
    for key in ("bet", "payout"):
        if key in out and not isinstance(out[key], int):
            out[key] = int(out[key])
    if "spun_at" in out and out["spun_at"] is not None and not isinstance(out["spun_at"], str):
        out["spun_at"] = out["spun_at"].isoformat()
    return out


def record_spin(
    args: Any,
    table_moniker: str,
    player_moniker: str,
    bet: int,
    payout: int,
    reels_json: list[list[str]],
    wins_json: list[dict[str, Any]],
) -> int:
    """Record a slot spin. Returns the new spin id."""
    with database.connect(args) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                """INSERT INTO $casino.__slot_spin
                       (table_moniker, player_moniker, bet, payout, reels, wins)
                       VALUES (:table_moniker, :player_moniker, :bet, :payout, :reels, :wins)
                       RETURNING id""",
                table_moniker=table_moniker,
                player_moniker=player_moniker,
                bet=bet,
                payout=payout,
                reels=Jsonb(reels_json),
                wins=Jsonb(wins_json),
            )
        )
        row = cur.fetchone()
        return int(row["id"])


def get_spin_history(
    args: Any,
    player_moniker: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the most recent spins for a player, newest first."""
    if limit <= 0:
        return []
    with database.connect(args) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                """SELECT id, table_moniker, player_moniker, bet, payout, reels, wins, spun_at
                       FROM $casino.__slot_spin
                       WHERE player_moniker = :player_moniker
                       ORDER BY spun_at DESC, id DESC
                       LIMIT :limit""",
                player_moniker=player_moniker,
                limit=limit,
            )
        )
        return [_coerce_row(dict(row)) for row in cur]


def get_table_history(
    args: Any,
    table_moniker: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the most recent spins at a table, newest first."""
    if limit <= 0:
        return []
    with database.connect(args) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                """SELECT id, table_moniker, player_moniker, bet, payout, reels, wins, spun_at
                       FROM $casino.__slot_spin
                       WHERE table_moniker = :table_moniker
                       ORDER BY spun_at DESC, id DESC
                       LIMIT :limit""",
                table_moniker=table_moniker,
                limit=limit,
            )
        )
        return [_coerce_row(dict(row)) for row in cur]
