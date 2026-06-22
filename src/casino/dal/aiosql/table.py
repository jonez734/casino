# casino/dal/async/table.py
# Async table data access layer

import random
from typing import Any, Dict, List, Optional

from bbsengine6 import database


COMPASS_POINTS = ["North", "South", "East", "West"]
PHONETIC_ALPHABET = [
    "Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot",
    "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima",
    "Mike", "November", "Oscar", "Papa", "Quebec", "Romeo",
    "Sierra", "Tango", "Uniform", "Victor", "Whiskey", "X-ray",
    "Yankee", "Zulu",
]


def generate_table_name() -> str:
    """Generate a random table name from compass points and phonetic alphabet."""
    return f"{random.choice(COMPASS_POINTS)}{random.choice(PHONETIC_ALPHABET)}"


async def create_table(
    args: Any,
    game_type: str,
    owner_moniker: str,
    min_bet: int = 10,
    max_bet: int = 1000,
    moniker: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new casino table."""
    if not moniker:
        moniker = f"{game_type}-{owner_moniker.lower()}"

    table_name = generate_table_name()

    rows = await database.async_query(
        args,
        database.query(
            "SELECT moniker FROM engine.__member WHERE moniker = :owner_moniker",
            owner_moniker=owner_moniker
        )
    )
    if not rows:
        from bbsengine6 import io
        io.echo(
            f"casino.dal.aiosql.table.create_table.100: Owner {owner_moniker} does not exist! Go away!",
            level="error"
        )
        return None

    rows = await database.async_query(
        args,
        database.query(
            "SELECT id FROM bank.__account WHERE moniker = :owner_moniker",
            owner_moniker=owner_moniker
        )
    )
    if rows:
        account_id = rows[0]["id"]
    else:
        rows = await database.async_query(
            args,
            database.query(
                "INSERT INTO bank.__account (moniker, balance) VALUES (:owner_moniker, 0) RETURNING id",
                owner_moniker=owner_moniker
            )
        )
        account_id = rows[0]["id"]

    await database.async_query(
        args,
        database.query(
            "INSERT INTO casino.__bank_table (table_moniker, bank_account_id) VALUES (:moniker, :account_id)",
            moniker=moniker, account_id=account_id
        )
    )

    rows = await database.async_query(
        args,
        """INSERT INTO $casino.__table (moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, location, status) 
           VALUES (:moniker, :game_type, :min_bet, :max_bet, :owner_moniker, NOW(), :account_id, :table_name, 'open') 
           RETURNING moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status, dealermodule, playermodule""",
        moniker=moniker, game_type=game_type, min_bet=min_bet, max_bet=max_bet, 
        owner_moniker=owner_moniker, account_id=account_id, table_name=table_name
    )
    row = rows[0]
    return {
        "moniker": row["moniker"],
        "type": row["type"],
        "minimumbet": row["minimumbet"],
        "maximumbet": row["maximumbet"],
        "ownermoniker": row["ownermoniker"],
        "ownersince": row["ownersince"],
        "accountid": row["accountid"],
        "cheat": row["cheat"],
        "cheatpercent": row["cheatpercent"],
        "attrs": row["attrs"] or {},
        "shoe_cards": row["shoe_cards"] or [],
        "shoe_uses": row["shoe_uses"] or 0,
        "location": row["location"],
        "status": row["status"],
        "dealermodule": row.get("dealermodule"),
        "playermodule": row.get("playermodule"),
    }


async def get_table(args: Any, moniker: str) -> Optional[Dict[str, Any]]:
    """Get table by moniker."""
    rows = await database.async_query(
        args,
        """SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status, dealermodule, playermodule 
           FROM $casino.__table WHERE moniker = :moniker""",
        moniker=moniker
    )
    if rows:
        row = rows[0]
        return {
            "moniker": row["moniker"],
            "type": row["type"],
            "minimumbet": row["minimumbet"],
            "maximumbet": row["maximumbet"],
            "ownermoniker": row["ownermoniker"],
            "ownersince": row["ownersince"],
            "accountid": row["accountid"],
            "cheat": row["cheat"],
            "cheatpercent": row["cheatpercent"],
            "attrs": row["attrs"] or {},
            "shoe_cards": row["shoe_cards"] or [],
            "shoe_uses": row["shoe_uses"] or 0,
            "location": row["location"],
            "status": row["status"],
            "dealermodule": row.get("dealermodule"),
            "playermodule": row.get("playermodule"),
        }
    return None


async def list_tables(args: Any, game_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all tables, optionally filtered by game type."""
    if game_type:
        rows = await database.async_query(
            args,
            """SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status, dealermodule, playermodule 
               FROM $casino.__table WHERE type = :game_type ORDER BY moniker""",
            game_type=game_type
        )
    else:
        rows = await database.async_query(
            args,
            """SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status, dealermodule, playermodule 
               FROM $casino.__table ORDER BY moniker"""
        )
    
    return [
        {
            "moniker": row["moniker"],
            "type": row["type"],
            "minimumbet": row["minimumbet"],
            "maximumbet": row["maximumbet"],
            "ownermoniker": row["ownermoniker"],
            "ownersince": row["ownersince"],
            "accountid": row["accountid"],
            "cheat": row["cheat"],
            "cheatpercent": row["cheatpercent"],
            "attrs": row["attrs"] or {},
            "shoe_cards": row["shoe_cards"] or [],
            "shoe_uses": row["shoe_uses"] or 0,
            "location": row["location"],
            "status": row["status"],
            "dealermodule": row.get("dealermodule"),
            "playermodule": row.get("playermodule"),
        }
        for row in rows
    ]


async def get_table_players(args: Any, moniker: str) -> List[str]:
    """Get list of player monikers at a table."""
    rows = await database.async_query(
        args,
        "SELECT playermoniker FROM $casino.__map_cardtable_player WHERE tablemoniker = :moniker",
        moniker=moniker
    )
    return [row["playermoniker"] for row in rows]


async def get_table_spectators(args: Any, moniker: str) -> List[str]:
    """Get list of spectator monikers at a table."""
    rows = await database.async_query(
        args,
        "SELECT playermoniker FROM $casino.__map_cardtable_player WHERE tablemoniker = :moniker AND role = 'spectator'",
        moniker=moniker
    )
    return [row["playermoniker"] for row in rows]


async def add_player_to_table(args: Any, moniker: str, player_moniker: str, role: str = "player") -> bool:
    """Add a player to a table."""
    rows = await database.async_query(
        args,
        """INSERT INTO $casino.__map_cardtable_player (tablemoniker, playermoniker, role, joinedat) 
           VALUES (:moniker, :player_moniker, :role, NOW()) 
           ON CONFLICT DO NOTHING RETURNING tablemoniker""",
        moniker=moniker, player_moniker=player_moniker, role=role
    )
    return len(rows) > 0


async def remove_player_from_table(args: Any, moniker: str, player_moniker: str) -> bool:
    """Remove a player from a table."""
    rows = await database.async_query(
        args,
        "DELETE FROM $casino.__map_cardtable_player WHERE tablemoniker = :moniker AND playermoniker = :player_moniker RETURNING tablemoniker",
        moniker=moniker, player_moniker=player_moniker
    )
    return len(rows) > 0


async def delete_table(args: Any, moniker: str) -> bool:
    """Delete a table."""
    rows = await database.async_query(
        args,
        "DELETE FROM $casino.__table WHERE moniker = :moniker RETURNING moniker",
        moniker=moniker
    )
    return len(rows) > 0


async def update_shoe(args: Any, moniker: str, cards: List[str], uses: int) -> None:
    """Update table shoe."""
    await database.async_query(
        args,
        "UPDATE $casino.__table SET shoe_cards = :cards, shoe_uses = :uses WHERE moniker = :moniker",
        moniker=moniker, cards=cards, uses=uses
    )


async def update_table(args: Any, moniker: str, **updates) -> Optional[Dict[str, Any]]:
    """Update table fields."""
    set_clauses = []
    params = {"moniker": moniker}
    
    for key, value in updates.items():
        set_clauses.append(f"{key} = :{key}")
        params[key] = value
    
    if not set_clauses:
        return await get_table(args, moniker)
    
    sql = f"UPDATE $casino.__table SET {', '.join(set_clauses)} WHERE moniker = :moniker RETURNING *"
    rows = await database.async_query(args, sql, **params)
    
    if rows:
        return await get_table(args, moniker)
    return None


async def reset_shoe(args: Any, moniker: str) -> bool:
    """Reset table shoe to new shuffled deck."""
    rows = await database.async_query(
        args,
        "UPDATE $casino.__table SET shoe_cards = NULL, shoe_uses = 0 WHERE moniker = :moniker RETURNING moniker",
        moniker=moniker
    )
    return len(rows) > 0


async def get_player_tables(args: Any, player_moniker: str) -> List[str]:
    """Get all tables a player is currently at."""
    rows = await database.async_query(
        args,
        "SELECT DISTINCT tablemoniker FROM $casino.__map_cardtable_player WHERE playermoniker = :player_moniker",
        player_moniker=player_moniker
    )
    return [row["tablemoniker"] for row in rows]
