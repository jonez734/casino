# casino/dal/async/table.py
# Async table data access layer
#
# All public functions in this module accept an optional ``pool`` keyword
# argument (CONN_POOL_PATTERN). When supplied, the function threads it into
# ``database.async_query(args, sql, pool=pool, ...)`` so the caller owns
# the pool. When absent, the legacy ``async_query(args, sql, ...)`` shape
# is used as a backward-compat fallback.

import random
from typing import Any, Optional

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
    hidden: bool = False,
    *,
    pool: Any = None,
) -> dict[str, Any]:
    """Create a new casino table.

    Args:
        hidden: If True, table is hidden from list_tables for non-sysop users.
        pool: Optional async pool (CONN_POOL_PATTERN)

    Returns the new table dict, or a sentinel dict with
    ``"__exists__": True`` when the moniker is already taken. The
    sentinel carries the existing row's full payload so callers can
    render stats without a second query.
    """
    if not moniker:
        moniker = f"{game_type}-{owner_moniker.lower()}"

    table_name = generate_table_name()

    rows = await database.async_query(
        args,
        database.query(
            "SELECT moniker, type, minimumbet, maximumbet, ownermoniker, "
            "ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, "
            "shoe_uses, location, status, hidden, dealermodule, playermodule "
            "FROM $casino.__table WHERE moniker = :m",
            m=moniker,
        ),
        pool=pool,
    )
    if rows:
        row = rows[0]
        sentinel = {
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
            "hidden": bool(row.get("hidden", False)),
            "dealermodule": row.get("dealermodule"),
            "playermodule": row.get("playermodule"),
            "__exists__": True,
        }
        return sentinel

    rows = await database.async_query(
        args,
        database.query(
            "SELECT moniker FROM engine.__member WHERE moniker = :owner_moniker",
            owner_moniker=owner_moniker
        ),
        pool=pool,
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
        ),
        pool=pool,
    )
    if rows:
        account_id = rows[0]["id"]
    else:
        rows = await database.async_query(
            args,
            database.query(
                "INSERT INTO bank.__account (moniker, balance) VALUES (:owner_moniker, 0) RETURNING id",
                owner_moniker=owner_moniker
            ),
            pool=pool,
        )
        account_id = rows[0]["id"]

    await database.async_query(
        args,
        database.query(
            "INSERT INTO casino.__bank_table (table_moniker, bank_account_id) VALUES (:moniker, :account_id)",
            moniker=moniker, account_id=account_id
        ),
        pool=pool,
    )

    rows = await database.async_query(
        args,
        """INSERT INTO $casino.__table (moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, location, status, hidden)
           VALUES (:moniker, :game_type, :min_bet, :max_bet, :owner_moniker, NOW(), :account_id, :table_name, 'open', :hidden)
           RETURNING moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status, hidden, dealermodule, playermodule""",
        pool=pool,
        moniker=moniker, game_type=game_type, min_bet=min_bet, max_bet=max_bet,
        owner_moniker=owner_moniker, account_id=account_id, table_name=table_name, hidden=hidden
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
        "hidden": bool(row.get("hidden", False)),
        "dealermodule": row.get("dealermodule"),
        "playermodule": row.get("playermodule"),
    }


async def get_table_stats(
    args: Any,
    moniker: str,
    game_type: str,
    surrender_multiplier: float = 0.5,
    *,
    pool: Any = None,
) -> dict[str, Any]:
    """Async mirror of :func:`casino.dal.table.get_table_stats`.

    Branches on ``game_type``; surrender_multiplier is forwarded to
    the blackjack aggregate only.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    if game_type == "slots":
        rows = await database.async_query(
            args,
            database.query(
                "SELECT COUNT(*) AS spins, "
                "COALESCE(SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), 0) AS wins, "
                "COALESCE(SUM(CASE WHEN payout = 0 THEN 1 ELSE 0 END), 0) AS losses, "
                "COALESCE(SUM(payout - bet), 0) AS net "
                "FROM $casino.__slot_spin WHERE table_moniker = :m",
                m=moniker,
            ),
            pool=pool,
        )
        if not rows or int(rows[0]["spins"] or 0) == 0:
            return {}
        row = rows[0]
        return {
            "spins": int(row["spins"]),
            "wins": int(row["wins"]),
            "losses": int(row["losses"]),
            "net": int(row["net"]),
        }
    if game_type == "blackjack":
        rows = await database.async_query(
            args,
            database.query(
                "SELECT COUNT(*) AS hands_played, "
                "COALESCE(SUM(CASE WHEN attrs->>'outcome' IN ('win','blackjack') THEN 1 ELSE 0 END), 0) AS wins, "
                "COALESCE(SUM(CASE WHEN attrs->>'outcome' IN ('loss','bust') THEN 1 ELSE 0 END), 0) AS losses, "
                "COALESCE(SUM(CASE WHEN attrs->>'outcome' = 'push' THEN 1 ELSE 0 END), 0) AS pushes, "
                "COALESCE(SUM(CASE WHEN attrs->>'outcome' = 'blackjack' THEN 1 ELSE 0 END), 0) AS blackjacks, "
                "COALESCE(SUM(CASE WHEN attrs->>'outcome' = 'bust' THEN 1 ELSE 0 END), 0) AS busts, "
                "COALESCE(SUM(CASE WHEN attrs->>'outcome' = 'surrender' THEN 1 ELSE 0 END), 0) AS surrenders, "
                "COALESCE(SUM(CASE "
                "  WHEN attrs->>'outcome' = 'blackjack' THEN (attrs->>'bet_amount')::numeric * 1.5 "
                "  WHEN attrs->>'outcome' = 'win'       THEN (attrs->>'bet_amount')::numeric "
                "  WHEN attrs->>'outcome' = 'push'      THEN 0 "
                "  WHEN attrs->>'outcome' IN ('loss','bust') THEN -(attrs->>'bet_amount')::numeric "
                "  WHEN attrs->>'outcome' = 'surrender' THEN -(attrs->>'bet_amount')::numeric * :surr_mult "
                "  ELSE 0 END), 0) AS net "
                "FROM $casino.__game "
                "WHERE tablemoniker = :m AND status = 'settled' "
                "  AND attrs->>'outcome' IS NOT NULL",
                m=moniker, surr_mult=surrender_multiplier,
            ),
            pool=pool,
        )
        if not rows or int(rows[0]["hands_played"] or 0) == 0:
            return {}
        row = rows[0]
        return {
            "hands_played": int(row["hands_played"]),
            "wins": int(row["wins"]),
            "losses": int(row["losses"]),
            "pushes": int(row["pushes"]),
            "blackjacks": int(row["blackjacks"]),
            "busts": int(row["busts"]),
            "surrenders": int(row["surrenders"]),
            "net": int(row["net"]),
        }
    if game_type in ("yahtzee", "tictactoe"):
        rows = await database.async_query(
            args,
            database.query(
                "SELECT COUNT(*) AS hands_played, "
                "COALESCE(SUM(CASE WHEN attrs->>'outcome' = 'win'  THEN 1 ELSE 0 END), 0) AS wins, "
                "COALESCE(SUM(CASE WHEN attrs->>'outcome' = 'loss' THEN 1 ELSE 0 END), 0) AS losses, "
                "COALESCE(SUM(CASE WHEN attrs->>'outcome' = 'draw' THEN 1 ELSE 0 END), 0) AS draws, "
                "COALESCE(SUM((attrs->>'net')::numeric), 0) AS net "
                "FROM $casino.__game "
                "WHERE tablemoniker = :m AND status IN ('settled','closed') "
                "  AND attrs->>'outcome' IS NOT NULL",
                m=moniker,
            ),
            pool=pool,
        )
        if not rows or int(rows[0]["hands_played"] or 0) == 0:
            return {}
        row = rows[0]
        return {
            "hands_played": int(row["hands_played"]),
            "wins": int(row["wins"]),
            "losses": int(row["losses"]),
            "draws": int(row["draws"]),
            "net": int(row["net"]),
        }
    return {}


async def get_table(args: Any, moniker: str, *, pool: Any = None) -> Optional[dict[str, Any]]:
    """Get table by moniker.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    rows = await database.async_query(
        args,
        """SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status, hidden, dealermodule, playermodule
           FROM $casino.__table WHERE moniker = :moniker""",
        pool=pool,
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
            "hidden": bool(row.get("hidden", False)),
            "dealermodule": row.get("dealermodule"),
            "playermodule": row.get("playermodule"),
        }
    return None


async def list_tables(
    args: Any,
    game_type: Optional[str] = None,
    include_hidden: bool = False,
    *,
    pool: Any = None,
) -> list[dict[str, Any]]:
    """List all tables, optionally filtered by game type.

    By default, hidden tables are excluded. Set ``include_hidden=True`` to
    include them (e.g. for sysops who need to see every table).

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    where_clauses = []
    params: dict[str, Any] = {}
    if game_type:
        where_clauses.append("type = :game_type")
        params["game_type"] = game_type
    if not include_hidden:
        where_clauses.append("(hidden IS NULL OR hidden = false)")
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sql = (
        "SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status, hidden, dealermodule, playermodule "
        f"FROM $casino.__table {where_sql} ORDER BY moniker"
    )
    rows = await database.async_query(args, sql, pool=pool, **params)

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
            "hidden": bool(row.get("hidden", False)),
            "dealermodule": row.get("dealermodule"),
            "playermodule": row.get("playermodule"),
        }
        for row in rows
    ]


async def get_table_players(args: Any, moniker: str, *, pool: Any = None) -> list[str]:
    """Get list of player monikers at a table.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    rows = await database.async_query(
        args,
        "SELECT playermoniker FROM $casino.__map_cardtable_player WHERE tablemoniker = :moniker",
        pool=pool,
        moniker=moniker
    )
    return [row["playermoniker"] for row in rows]


async def get_table_spectators(args: Any, moniker: str, *, pool: Any = None) -> list[str]:
    """Get list of spectator monikers at a table.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    rows = await database.async_query(
        args,
        "SELECT playermoniker FROM $casino.__map_cardtable_player WHERE tablemoniker = :moniker AND role = 'spectator'",
        pool=pool,
        moniker=moniker
    )
    return [row["playermoniker"] for row in rows]


async def add_player_to_table(args: Any, moniker: str, player_moniker: str, role: str = "player", *, pool: Any = None) -> bool:
    """Add a player to a table.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    rows = await database.async_query(
        args,
        """INSERT INTO $casino.__map_cardtable_player (tablemoniker, playermoniker, role, joinedat)
           VALUES (:moniker, :player_moniker, :role, NOW())
           ON CONFLICT DO NOTHING RETURNING tablemoniker""",
        pool=pool,
        moniker=moniker, player_moniker=player_moniker, role=role
    )
    return len(rows) > 0


async def remove_player_from_table(args: Any, moniker: str, player_moniker: str, *, pool: Any = None) -> bool:
    """Remove a player from a table.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    rows = await database.async_query(
        args,
        "DELETE FROM $casino.__map_cardtable_player WHERE tablemoniker = :moniker AND playermoniker = :player_moniker RETURNING tablemoniker",
        pool=pool,
        moniker=moniker, player_moniker=player_moniker
    )
    return len(rows) > 0


async def delete_table(args: Any, moniker: str, *, pool: Any = None) -> bool:
    """Delete a table.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    rows = await database.async_query(
        args,
        "DELETE FROM $casino.__table WHERE moniker = :moniker RETURNING moniker",
        pool=pool,
        moniker=moniker
    )
    return len(rows) > 0


async def update_shoe(args: Any, moniker: str, cards: list[str], uses: int, *, pool: Any = None) -> None:
    """Update table shoe.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    await database.async_query(
        args,
        "UPDATE $casino.__table SET shoe_cards = :cards, shoe_uses = :uses WHERE moniker = :moniker",
        pool=pool,
        moniker=moniker, cards=cards, uses=uses
    )


async def update_table(args: Any, moniker: str, *, pool: Any = None, **updates) -> Optional[dict[str, Any]]:
    """Update table fields.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
        **updates: Column updates.
    """
    set_clauses = []
    params = {"moniker": moniker}

    for key, value in updates.items():
        set_clauses.append(f"{key} = :{key}")
        params[key] = value

    if not set_clauses:
        return await get_table(args, moniker, pool=pool)

    sql = f"UPDATE $casino.__table SET {', '.join(set_clauses)} WHERE moniker = :moniker RETURNING *"
    rows = await database.async_query(args, sql, pool=pool, **params)

    if rows:
        return await get_table(args, moniker, pool=pool)
    return None


async def reset_shoe(args: Any, moniker: str, *, pool: Any = None) -> bool:
    """Reset table shoe to new shuffled deck.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    rows = await database.async_query(
        args,
        "UPDATE $casino.__table SET shoe_cards = NULL, shoe_uses = 0 WHERE moniker = :moniker RETURNING moniker",
        pool=pool,
        moniker=moniker
    )
    return len(rows) > 0


async def get_player_tables(args: Any, player_moniker: str, *, pool: Any = None) -> list[str]:
    """Get all tables a player is currently at.

    Args:
        pool: Optional async pool (CONN_POOL_PATTERN)
    """
    rows = await database.async_query(
        args,
        "SELECT DISTINCT tablemoniker FROM $casino.__map_cardtable_player WHERE playermoniker = :player_moniker",
        pool=pool,
        player_moniker=player_moniker
    )
    return [row["tablemoniker"] for row in rows]
