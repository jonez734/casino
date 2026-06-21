# casino/dal/table.py
# Table data access layer

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


def create_table(
    args: Any,
    game_type: str,
    owner_moniker: str,
    min_bet: int = 10,
    max_bet: int = 1000,
    moniker: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new casino table.
    
    Args:
        args: Application args
        game_type: Type of game (blackjack, poker, etc.)
        owner_moniker: Owner of the table
        min_bet: Minimum bet
        max_bet: Maximum bet
        moniker: Unique text identifier (auto-generated if not provided)
        
    Returns:
        Table dict with moniker, game_type, owner, etc.
    """
    if not moniker:
        moniker = f"{game_type}-{owner_moniker.lower()}"

    table_name = generate_table_name()
    account_moniker = f"table:{moniker}"

    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "INSERT INTO $bank.__account (moniker, balance) VALUES (:account_moniker, 0) RETURNING id",
                    account_moniker=account_moniker
                )
            )
            account_row = cur.fetchone()
            account_id = account_row["id"]

            cur.execute(
                database.query(
                    "INSERT INTO $casino.__table (moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, location, status) VALUES (:moniker, :game_type, :min_bet, :max_bet, :owner_moniker, NOW(), :account_id, :table_name, 'open') RETURNING moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status",
                    moniker=moniker, game_type=game_type, min_bet=min_bet, max_bet=max_bet, owner_moniker=owner_moniker, account_id=account_id, table_name=table_name
                )
            )
            row = cur.fetchone()
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
            }


def get_table(args: Any, moniker: str) -> Optional[Dict[str, Any]]:
    """Get table by moniker."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status FROM $casino.__table WHERE moniker = :moniker",
                    moniker=moniker
                )
            )
            row = cur.fetchone()
            if row:
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
                }
            return None


def list_tables(args: Any, game_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List all tables, optionally filtered by game type.
    
    Returns:
        List of table dicts
    """
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            if game_type:
                cur.execute(
                    database.query(
                        "SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status FROM $casino.__table WHERE type = :game_type ORDER BY moniker",
                        game_type=game_type
                    )
                )
            else:
                cur.execute(
                    database.query(
                        "SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status FROM $casino.__table ORDER BY moniker"
                    )
                )
            
            tables = []
            for row in cur:
                tables.append({
                    "moniker": row["moniker"],
                    "type": row["type"],
                    "minimumbet": int(row["minimumbet"]) if row["minimumbet"] else 0,
                    "maximumbet": int(row["maximumbet"]) if row["maximumbet"] else 0,
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
                })
            return tables


def get_table_players(args: Any, moniker: str) -> List[str]:
    """Get list of player monikers at a table (via active game)."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT DISTINCT m.playermoniker FROM $casino.mapgameplayer m JOIN $casino.__game g ON g.id = m.gameid WHERE g.tablemoniker = :moniker AND g.status NOT IN ('settled', 'cancelled')",
                    moniker=moniker
                )
            )
            return [row["playermoniker"] for row in cur]


def get_table_spectators(args: Any, moniker: str) -> List[str]:
    """Get list of spectator monikers watching table."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT DISTINCT p.playermoniker FROM $casino.map_cardtable_player p WHERE p.cardtablemoniker = :moniker",
                    moniker=moniker
                )
            )
            return [row["playermoniker"] for row in cur]


def add_player_to_table(
    args: Any, moniker: str, player_moniker: str
) -> bool:
    """Add player to table (sitting down). Player must already be in a game."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "INSERT INTO $casino.map_cardtable_player (cardtablemoniker, playermoniker) VALUES (:moniker, :player_moniker) ON CONFLICT DO NOTHING",
                    moniker=moniker, player_moniker=player_moniker
                )
            )
            return True


def remove_player_from_table(args: Any, moniker: str, player_moniker: str) -> bool:
    """Remove player from table (standing up)."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "DELETE FROM $casino.mapgameplayer m USING $casino.__game g WHERE m.gameid = g.id AND g.tablemoniker = :moniker AND m.playermoniker = :player_moniker",
                    moniker=moniker, player_moniker=player_moniker
                )
            )
            return cur.rowcount > 0


def delete_table(args: Any, moniker: str) -> bool:
    """Delete a table (owner only)."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(database.query("DELETE FROM $casino.__game WHERE tablemoniker = :moniker", moniker=moniker))
            cur.execute(database.query("DELETE FROM $casino.__table WHERE moniker = :moniker", moniker=moniker))
            return cur.rowcount > 0


def update_shoe(args: Any, moniker: str, cards: List[str], uses: int) -> None:
    """Update shoe state for a table."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__table SET shoe_cards = :cards, shoe_uses = :uses WHERE moniker = :moniker",
                    cards=cards, uses=uses, moniker=moniker
                )
            )


def update_table(args: Any, moniker: str, **updates) -> Optional[Dict[str, Any]]:
    """Update table fields (moniker, minimumbet, maximumbet, status).
    
    Args:
        args: Application args
        moniker: Current table moniker
        **updates: Fields to update (new_moniker, minimumbet, maximumbet, status)
    
    Returns:
        Updated table dict or None if not found
    """
    set_clauses = []
    values = []
    
    if "new_moniker" in updates:
        set_clauses.append("moniker = %s")
        values.append(updates["new_moniker"])
    if "minimumbet" in updates:
        set_clauses.append("minimumbet = %s")
        values.append(updates["minimumbet"])
    if "maximumbet" in updates:
        set_clauses.append("maximumbet = %s")
        values.append(updates["maximumbet"])
    if "status" in updates:
        set_clauses.append("status = %s")
        values.append(updates["status"])
    
    if not set_clauses:
        return get_table(args, moniker)
    
    values.append(moniker)
    
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            sql = f"UPDATE casino.__table SET {', '.join(set_clauses)} WHERE moniker = %s RETURNING moniker"
            cur.execute(sql, values)
            if cur.rowcount == 0:
                return None
    
    new_moniker = updates.get("new_moniker", moniker)
    return get_table(args, new_moniker)


def reset_shoe(args: Any, moniker: str) -> bool:
    """Reset table shoe (clear cards, reset uses to 0).
    
    Args:
        args: Application args
        moniker: Table moniker
    
    Returns:
        True if shoe was reset, False if table not found
    """
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__table SET shoe_cards = NULL, shoe_uses = 0 WHERE moniker = :moniker",
                    moniker=moniker
                )
            )
            return cur.rowcount > 0
