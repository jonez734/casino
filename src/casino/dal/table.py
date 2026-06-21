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

    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                """INSERT INTO casino.__table 
                   (moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, bank, earnings, location)
                   VALUES (%s, %s, %s, %s, %s, NOW(), 0, 0, %s)
                   RETURNING moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, bank, earnings, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location""",
                (moniker, game_type, min_bet, max_bet, owner_moniker, table_name),
            )
            row = cur.fetchone()
            return {
                "moniker": row["moniker"],
                "type": row["type"],
                "minimumbet": row["minimumbet"],
                "maximumbet": row["maximumbet"],
                "ownermoniker": row["ownermoniker"],
                "ownersince": row["ownersince"],
                "bank": row["bank"],
                "earnings": row["earnings"],
                "cheat": row["cheat"],
                "cheatpercent": row["cheatpercent"],
                "attrs": row["attrs"] or {},
                "shoe_cards": row["shoe_cards"] or [],
                "shoe_uses": row["shoe_uses"] or 0,
                "location": row["location"],
            }


def get_table(args: Any, moniker: str) -> Optional[Dict[str, Any]]:
    """Get table by moniker."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                """SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, 
                          bank, earnings, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location
                   FROM casino.__table WHERE moniker = %s""",
                (moniker,),
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
                    "bank": row["bank"],
                    "earnings": row["earnings"],
                    "cheat": row["cheat"],
                    "cheatpercent": row["cheatpercent"],
                    "attrs": row["attrs"] or {},
                    "shoe_cards": row["shoe_cards"] or [],
                    "shoe_uses": row["shoe_uses"] or 0,
                    "location": row["location"],
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
                    """SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince,
                              bank, earnings, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location
                       FROM casino.__table WHERE type = %s ORDER BY moniker""",
                    (game_type,),
                )
            else:
                cur.execute(
                    """SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince,
                              bank, earnings, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location
                       FROM casino.__table ORDER BY moniker"""
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
                    "bank": int(row["bank"]) if row["bank"] else 0,
                    "earnings": int(row["earnings"]) if row["earnings"] else 0,
                    "cheat": row["cheat"],
                    "cheatpercent": row["cheatpercent"],
                    "attrs": row["attrs"] or {},
                    "shoe_cards": row["shoe_cards"] or [],
                    "shoe_uses": row["shoe_uses"] or 0,
                    "location": row["location"],
                })
            return tables


def get_table_players(args: Any, moniker: str) -> List[str]:
    """Get list of player monikers at a table (via active game)."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                """SELECT DISTINCT m.playermoniker 
                   FROM casino.mapgameplayer m
                   JOIN casino.__game g ON g.id = m.gameid
                   WHERE g.tablemoniker = %s AND g.status NOT IN ('settled', 'cancelled')""",
                (moniker,),
            )
            return [row["playermoniker"] for row in cur]


def get_table_spectators(args: Any, moniker: str) -> List[str]:
    """Get list of spectator monikers watching table."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                """SELECT DISTINCT p.playermoniker 
                   FROM casino.map_cardtable_player p
                   WHERE p.cardtablemoniker = %s""",
                (moniker,),
            )
            return [row["playermoniker"] for row in cur]


def add_player_to_table(
    args: Any, moniker: str, player_moniker: str
) -> bool:
    """Add player to table (sitting down). Player must already be in a game."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                """INSERT INTO casino.map_cardtable_player (cardtablemoniker, playermoniker)
                   VALUES (%s, %s)
                   ON CONFLICT DO NOTHING""",
                (moniker, player_moniker),
            )
            return True


def remove_player_from_table(args: Any, moniker: str, player_moniker: str) -> bool:
    """Remove player from table (standing up)."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                """DELETE FROM casino.mapgameplayer m 
                   USING casino.__game g 
                   WHERE m.gameid = g.id AND g.tablemoniker = %s AND m.playermoniker = %s""",
                (moniker, player_moniker),
            )
            return cur.rowcount > 0


def delete_table(args: Any, moniker: str) -> bool:
    """Delete a table (owner only)."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute("DELETE FROM casino.__game WHERE tablemoniker = %s", (moniker,))
            cur.execute("DELETE FROM casino.__table WHERE moniker = %s", (moniker,))
            return cur.rowcount > 0


def update_shoe(args: Any, moniker: str, cards: List[str], uses: int) -> None:
    """Update shoe state for a table."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                "UPDATE casino.__table SET shoe_cards = %s, shoe_uses = %s WHERE moniker = %s",
                (cards, uses, moniker),
            )
