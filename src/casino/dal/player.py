# casino/dal/player.py
# Player data access layer

from typing import Any, Dict, List, Optional

from bbsengine6 import database, io
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
                "SELECT membermoniker, location, lastplayed, attrs FROM $casino.player WHERE membermoniker = :moniker",
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

        io.echo("casino.dal.player.100: about to insert into __player", level="debug")
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
                    "SELECT membermoniker, location, lastplayed, attrs FROM $casino.player WHERE membermoniker = :moniker",
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


def test_schema_permissions(args: Any) -> dict:
    """Test SELECT permissions on all casino tables/views."""
    results = {}
    tables_and_views = [
        ("casino.player", True),
        ("casino.table", True),
        ("casino.game", True),
        ("casino.hand", True),
        ("casino.betlog", True),
        ("casino.log", True),
        ("casino.map_game_player", True),
        ("casino.map_cardtable_player", True),
        ("casino.__player", False),
        ("casino.__table", False),
        ("casino.__game", False),
        ("casino.__hand", False),
        ("casino.__betlog", False),
        ("casino.__log", False),
    ]

    for table in tables_and_views:
        table_name = table[0]
        is_view = table[1]
        query = f"SELECT 1 FROM {table_name} LIMIT 1"
        try:
            with database.connect(args) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(query)
                    cur.fetchone()
                    results[table_name] = "OK"
                    io.echo(f"test_schema_permissions: {table_name} - OK", level="info")
        except Exception as e:
            error_msg = str(e)
            results[table_name] = f"ERROR: {error_msg}"
            io.echo(f"test_schema_permissions: {table_name} - ERROR: {error_msg}", level="error")

    return results


ALLOWED_STATS = {
    "wins", "losses", "pushes", "net",
    "blackjack.blackjacks", "blackjack.busts", "blackjack.surrenders", "blackjack.hands_played",
}


def get_player_stats(args: Any, moniker: str) -> Dict[str, Any]:
    """Get player statistics from database.
    
    Args:
        args: Application args (for database connection)
        moniker: BBS member moniker
        
    Returns:
        Dict of stat_name -> value (e.g. {"wins": 10, "losses": 5, "net": 500})
    """
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT stats FROM $casino.__player WHERE membermoniker = :moniker",
                    moniker=moniker
                )
            )
            row = cur.fetchone()
            if row and row["stats"]:
                return dict(row["stats"])
            return {}


def update_player_stats(args: Any, moniker: str, stats: Dict[str, Any]) -> None:
    """Replace player statistics entirely.
    
    Args:
        args: Application args (for database connection)
        moniker: BBS member moniker
        stats: Dict of stat_name -> value to set
    """
    invalid_stats = set(stats.keys()) - ALLOWED_STATS
    if invalid_stats:
        raise ValueError(f"Invalid stat names: {invalid_stats}. Allowed: {ALLOWED_STATS}")
    
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__player SET stats = :stats WHERE membermoniker = :moniker",
                    moniker=moniker, stats=Jsonb(stats)
                )
            )


def increment_stat(args: Any, moniker: str, stat_name: str, amount: int = 1) -> None:
    """Atomically increment a player stat.
    
    Args:
        args: Application args (for database connection)
        moniker: BBS member moniker
        stat_name: Name of stat to increment (must be in ALLOWED_STATS)
        amount: Positive integer to add (default 1)
        
    Raises:
        ValueError: If stat_name is not in ALLOWED_STATS or amount <= 0
    """
    if stat_name not in ALLOWED_STATS:
        raise ValueError(
            f"Invalid stat name: '{stat_name}'. Allowed stats: {sorted(ALLOWED_STATS)}"
        )
    
    if stat_name == "net":
        if not isinstance(amount, int):
            raise ValueError(f"amount must be an integer for net, got: {type(amount)}")
    else:
        if not isinstance(amount, int) or amount <= 0:
            raise ValueError(f"amount must be a positive integer, got: {amount}")
    
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    """UPDATE $casino.__player 
                       SET stats = stats || jsonb_build_object(:stat_name, COALESCE((stats->>:stat_name)::int, 0) + :amount)
                       WHERE membermoniker = :moniker""",
                    moniker=moniker, stat_name=stat_name, amount=amount
                )
            )
