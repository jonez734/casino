# casino/dal/async/player.py
# Async player data access layer

from typing import Any, Dict, Optional

from bbsengine6 import database


async def get_or_create_player(
    args: Any,
    moniker: str,
) -> Dict[str, Any]:
    """Get or create a player."""
    rows = await database.async_query(
        args,
        """INSERT INTO $casino.__player (moniker, balance, createdat, lastplayed) 
           VALUES (:moniker, 1000, NOW(), NOW()) 
           ON CONFLICT (moniker) DO UPDATE SET lastplayed = NOW() 
           RETURNING moniker, balance, createdat, lastplayed""",
        moniker=moniker
    )
    row = rows[0]
    return {
        "moniker": row["moniker"],
        "balance": row["balance"],
        "createdat": row["createdat"],
        "lastplayed": row["lastplayed"],
    }


async def get_player_by_moniker(args: Any, moniker: str) -> Optional[Dict[str, Any]]:
    """Get a player by moniker."""
    rows = await database.async_query(
        args,
        """SELECT moniker, balance, createdat, lastplayed 
           FROM $casino.__player 
           WHERE moniker = :moniker""",
        moniker=moniker
    )
    if rows:
        row = rows[0]
        return {
            "moniker": row["moniker"],
            "balance": row["balance"],
            "createdat": row["createdat"],
            "lastplayed": row["lastplayed"],
        }
    return None


async def get_player_balance(args: Any, moniker: str) -> int:
    """Get a player's balance."""
    rows = await database.async_query(
        args,
        "SELECT balance FROM $casino.__player WHERE moniker = :moniker",
        moniker=moniker
    )
    if rows:
        return rows[0]["balance"] or 0
    return 0


async def update_player_lastplayed(args: Any, moniker: str) -> None:
    """Update player's lastplayed timestamp."""
    await database.async_query(
        args,
        "UPDATE $casino.__player SET lastplayed = NOW() WHERE moniker = :moniker",
        moniker=moniker
    )


async def test_schema_permissions(args: Any) -> dict:
    """Test schema permissions."""
    rows = await database.async_query(
        args,
        "SELECT current_user as user, current_database() as database"
    )
    if rows:
        return {"user": rows[0]["user"], "database": rows[0]["database"]}
    return {}
