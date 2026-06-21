# casino/dal/player.py
# Player data access layer

from typing import Any, Dict, List, Optional

from bbsengine6 import database
from bbsengine6.database import Jsonb


def get_or_create_player(
    args: Any, moniker: str
) -> Dict[str, Any]:
    """
    Get existing player or create new one for BBS member.
    
    Args:
        args: Application args (for database connection)
        moniker: BBS member moniker
        
    Returns:
        Player dict with moniker, balance, etc.
    """
    
    def _work(cur):
        cur.execute(
            database.query(
                "SELECT membermoniker, location, lastplayed, attrs FROM $casino.__player WHERE membermoniker = :moniker",
                moniker=moniker
            )
        )
        row = cur.fetchone()
        if row:
            return {
                "membermoniker": row["membermoniker"],
                "location": row["location"],
                "lastplayed": row["lastplayed"],
                "attrs": row["attrs"] or {},
            }
        
        cur.execute(
            database.query(
                "INSERT INTO $casino.__player (membermoniker, location, attrs) VALUES (:moniker, :location, :attrs) RETURNING membermoniker",
                moniker=moniker, location="casino", attrs=Jsonb({})
            )
        )
        row = cur.fetchone()
        return {
            "membermoniker": row["membermoniker"],
            "location": "casino",
            "lastplayed": None,
            "attrs": {},
        }
    
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            return _work(cur)


def get_player_by_moniker(args: Any, moniker: str) -> Optional[Dict[str, Any]]:
    """Get player by moniker."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT membermoniker, location, lastplayed, attrs FROM $casino.__player WHERE membermoniker = :moniker",
                    moniker=moniker
                )
            )
            row = cur.fetchone()
            if row:
                return {
                    "membermoniker": row["membermoniker"],
                    "location": row["location"],
                    "lastplayed": row["lastplayed"],
                    "attrs": row["attrs"] or {},
                }
            return None


def get_player_balance(args: Any, moniker: str) -> int:
    """Get player's casino balance (from member.credits)."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT credits FROM $engine.__member WHERE moniker = :moniker",
                    moniker=moniker
                )
            )
            row = cur.fetchone()
            return int(row["credits"]) if row else 0


def update_player_lastplayed(args: Any, moniker: str) -> None:
    """Update player's last played timestamp."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__player SET lastplayed = NOW() WHERE membermoniker = :moniker",
                    moniker=moniker
                )
            )
