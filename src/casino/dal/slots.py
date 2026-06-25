# casino/dal/slots.py
# Slot spin history and paytable config DAL.

from __future__ import annotations

from typing import Any, Dict, List

from bbsengine6 import database
from bbsengine6.database import Jsonb


def record_spin(
    args: Any,
    table_moniker: str,
    player_moniker: str,
    bet: int,
    payout: int,
    reels_json: List[List[str]],
    wins_json: List[Dict[str, Any]],
) -> int:
    """Record a slot spin. Returns the new spin id."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
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
) -> List[Dict[str, Any]]:
    """Return the most recent spins for a player, newest first."""
    if limit <= 0:
        return []
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
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
            return [dict(row) for row in cur]


def get_table_history(
    args: Any,
    table_moniker: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return the most recent spins at a table, newest first."""
    if limit <= 0:
        return []
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
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
            return [dict(row) for row in cur]
