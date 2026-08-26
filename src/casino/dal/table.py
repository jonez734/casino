# casino/dal/table.py
# Table data access layer
#
# All public functions in this module accept an optional ``pool`` keyword
# argument (CONN_POOL_PATTERN). When supplied, the function threads it into
# ``database.connect(args, pool=pool)`` so the caller owns the pool. When
# absent, the legacy ``database.connect(args)`` shape is used as a
# backward-compat fallback.

import random
from typing import Any, Optional

from bbsengine6 import database, io

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


def _connect_ctx(args: Any, pool: Any):
    """CONN_POOL_PATTERN helper: pick connect(args, pool=pool) when pool
    is supplied, else fall back to ``database.connect(args)``.
    """
    if pool is None:
        return database.connect(args)
    return database.connect(args, pool=pool)


def _row_to_table_dict(row: Any) -> dict[str, Any]:
    """Map a ``casino.__table`` SELECT row to the canonical table dict.

    Used by ``get_table`` and the duplicate-detection sentinel in
    ``create_table`` so both return the same shape.
    """
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
    }


def create_table(
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
    """
    Create a new casino table.

    Args:
        args: Application args
        game_type: Type of game (blackjack, poker, etc.)
        owner_moniker: Owner of the table
        min_bet: Minimum bet
        max_bet: Maximum bet
        moniker: Unique text identifier (auto-generated if not provided)
        hidden: If True, table is hidden from list_tables for non-sysops
        pool: Optional connection pool (CONN_POOL_PATTERN)

    Returns:
        Table dict with moniker, game_type, owner, etc., or a sentinel
        dict with ``"__exists__": True`` when the moniker is already
        taken. The sentinel includes the existing row's full
        ``_row_to_table_dict`` shape so callers can render stats
        without a second query.
    """
    if not moniker:
        moniker = f"{game_type}-{owner_moniker.lower()}"

    table_name = generate_table_name()

    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "SELECT moniker, type, minimumbet, maximumbet, ownermoniker, "
                "ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, "
                "shoe_uses, location, status, hidden "
                "FROM $casino.__table WHERE moniker = :m",
                m=moniker,
            )
        )
        existing_row = cur.fetchone()
        if existing_row is not None:
            sentinel = _row_to_table_dict(existing_row)
            sentinel["__exists__"] = True
            return sentinel

        cur.execute(
            database.query(
                "SELECT moniker FROM engine.__member WHERE moniker = :owner_moniker",
                owner_moniker=owner_moniker
            )
        )
        if cur.fetchone() is None:
            io.echo(
                f"casino.dal.table.create_table.100: Owner {owner_moniker} does not exist! Go away!",
                level="error"
            )
            return None

        cur.execute(
            database.query(
                "SELECT id FROM bank.__account WHERE moniker = :owner_moniker",
                owner_moniker=owner_moniker
            )
        )
        account_row = cur.fetchone()
        if account_row:
            account_id = account_row["id"]
        else:
            cur.execute(
                database.query(
                    "INSERT INTO bank.__account (moniker, balance) VALUES (:owner_moniker, 0) RETURNING id",
                    owner_moniker=owner_moniker
                )
            )
            account_row = cur.fetchone()
            account_id = account_row["id"]

        cur.execute(
            database.query(
                "INSERT INTO casino.__bank_table (table_moniker, bank_account_id) VALUES (:moniker, :account_id)",
                moniker=moniker, account_id=account_id
            )
        )

        cur.execute(
            database.query(
                "INSERT INTO $casino.__table (moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, location, status, hidden) VALUES (:moniker, :game_type, :min_bet, :max_bet, :owner_moniker, NOW(), :account_id, :table_name, 'open', :hidden) RETURNING moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status, hidden",
                moniker=moniker, game_type=game_type, min_bet=min_bet, max_bet=max_bet, owner_moniker=owner_moniker, account_id=account_id, table_name=table_name, hidden=hidden
            )
        )
        row = cur.fetchone()
        return _row_to_table_dict(row)


def get_table(args: Any, moniker: str, *, pool: Any = None) -> Optional[dict[str, Any]]:
    """Get table by moniker.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status, hidden FROM $casino.__table WHERE moniker = :moniker",
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
                    "hidden": row.get("hidden", False),
                }
            return None


def list_tables(
    args: Any,
    game_type: Optional[str] = None,
    include_hidden: bool = False,
    *,
    pool: Any = None,
) -> list[dict[str, Any]]:
    """
    List all tables, optionally filtered by game type.

    By default, hidden tables are excluded. Set ``include_hidden=True`` to
    include them (e.g. for sysops who need to see every table).

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)

    Returns:
        List of table dicts
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            where_clauses = []
            params: dict[str, Any] = {}
            if game_type:
                where_clauses.append("type = :game_type")
                params["game_type"] = game_type
            if not include_hidden:
                where_clauses.append("(hidden IS NULL OR hidden = false)")
            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            sql = (
                "SELECT moniker, type, minimumbet, maximumbet, ownermoniker, ownersince, accountid, cheat, cheatpercent, attrs, shoe_cards, shoe_uses, location, status, hidden "
                f"FROM $casino.__table {where_sql} ORDER BY moniker"
            )
            cur.execute(database.query(sql, **params) if params else database.query(sql))

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
                    "hidden": bool(row.get("hidden", False)),
                })
            return tables


def get_table_players(args: Any, moniker: str, *, pool: Any = None) -> list[str]:
    """Get list of player monikers at a table (via active game).

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT DISTINCT m.playermoniker FROM $casino.map_game_player m JOIN $casino.__game g ON g.id = m.gameid WHERE g.tablemoniker = :moniker AND g.status NOT IN ('settled', 'cancelled')",
                    moniker=moniker
                )
            )
            return [row["playermoniker"] for row in cur]


def get_table_spectators(args: Any, moniker: str, *, pool: Any = None) -> list[str]:
    """Get list of spectator monikers watching table.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT DISTINCT p.playermoniker FROM $casino.map_cardtable_player p WHERE p.cardtablemoniker = :moniker",
                    moniker=moniker
                )
            )
            return [row["playermoniker"] for row in cur]


def add_player_to_table(
    args: Any, moniker: str, player_moniker: str, *, pool: Any = None
) -> bool:
    """Add player to table (sitting down). Player must already be in a game.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "INSERT INTO $casino.map_cardtable_player (cardtablemoniker, playermoniker) VALUES (:moniker, :player_moniker) ON CONFLICT DO NOTHING",
                    moniker=moniker, player_moniker=player_moniker
                )
            )
            return True


def remove_player_from_table(args: Any, moniker: str, player_moniker: str, *, pool: Any = None) -> bool:
    """Remove player from table (standing up).

    Cleans both ``map_game_player`` (game-level seat; blackjack) and
    ``map_cardtable_player`` (table-level seat; single-seater games
    such as slots). Returns True iff at least one row was removed.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "DELETE FROM $casino.map_game_player m USING $casino.__game g "
                "WHERE m.gameid = g.id AND g.tablemoniker = :moniker "
                "AND m.playermoniker = :player_moniker",
                moniker=moniker, player_moniker=player_moniker,
            )
        )
        game_rows = cur.rowcount
        cur.execute(
            database.query(
                "DELETE FROM $casino.map_cardtable_player "
                "WHERE cardtablemoniker = :moniker AND playermoniker = :player_moniker",
                moniker=moniker, player_moniker=player_moniker,
            )
        )
        ct_rows = cur.rowcount
        return (game_rows + ct_rows) > 0


def delete_table(args: Any, moniker: str, *, pool: Any = None) -> bool:
    """Delete a table (owner only).

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(database.query("DELETE FROM $casino.__game WHERE tablemoniker = :moniker", moniker=moniker))
        cur.execute(database.query("DELETE FROM $casino.__table WHERE moniker = :moniker", moniker=moniker))
        return cur.rowcount > 0


def update_shoe(args: Any, moniker: str, cards: list[str], uses: int, *, pool: Any = None) -> None:
    """Update shoe state for a table.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE $casino.__table SET shoe_cards = :cards, shoe_uses = :uses WHERE moniker = :moniker",
                cards=cards, uses=uses, moniker=moniker
            )
        )


def update_table(args: Any, moniker: str, *, pool: Any = None, **updates) -> Optional[dict[str, Any]]:
    """Update table fields (moniker, minimumbet, maximumbet, status, hidden).

    Args:
        args: Application args
        moniker: Current table moniker
        pool: Optional connection pool (CONN_POOL_PATTERN)
        **updates: Fields to update (new_moniker, minimumbet, maximumbet, status, hidden)

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
    if "hidden" in updates:
        set_clauses.append("hidden = %s")
        values.append(updates["hidden"])

    if not set_clauses:
        return get_table(args, moniker, pool=pool)

    values.append(moniker)

    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        sql = f"UPDATE casino.__table SET {', '.join(set_clauses)} WHERE moniker = %s RETURNING moniker"
        cur.execute(sql, values)
        if cur.rowcount == 0:
            return None

    new_moniker = updates.get("new_moniker", moniker)
    return get_table(args, new_moniker, pool=pool)


def reset_shoe(args: Any, moniker: str, *, pool: Any = None) -> bool:
    """Reset table shoe (clear cards, reset uses to 0).

    Args:
        args: Application args
        moniker: Table moniker
        pool: Optional connection pool (CONN_POOL_PATTERN)

    Returns:
        True if shoe was reset, False if table not found
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE $casino.__table SET shoe_cards = NULL, shoe_uses = 0 WHERE moniker = :moniker",
                moniker=moniker
            )
        )
        return cur.rowcount > 0


def _stats_from_slot_spins(args: Any, moniker: str, *, pool: Any = None) -> dict[str, Any]:
    """Aggregate stats for a slots table from ``casino.__slot_spin``.

    Returns ``{spins, wins, losses, net}``. ``wins`` counts spins with
    payout > 0; ``losses`` counts spins with payout == 0; ``net`` is
    ``sum(payout - bet)`` over the table.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "SELECT COUNT(*) AS spins, "
                "COALESCE(SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), 0) AS wins, "
                "COALESCE(SUM(CASE WHEN payout = 0 THEN 1 ELSE 0 END), 0) AS losses, "
                "COALESCE(SUM(payout - bet), 0) AS net "
                "FROM $casino.__slot_spin WHERE table_moniker = :m",
                m=moniker,
            )
        )
        row = cur.fetchone()
        if not row or int(row["spins"] or 0) == 0:
            return {}
        return {
            "spins": int(row["spins"]),
            "wins": int(row["wins"]),
            "losses": int(row["losses"]),
            "net": int(row["net"]),
        }


def _stats_from_blackjack_games(
    args: Any, moniker: str, surrender_multiplier: float, *, pool: Any = None
) -> dict[str, Any]:
    """Aggregate stats for a blackjack table from ``casino.__game``.

    Counts settled games where ``attrs->>'outcome'`` is set; the
    settle path writes ``outcome`` (one of ``win``, ``loss``, ``push``,
    ``blackjack``, ``bust``, ``surrender``) and ``bet_amount`` per
    settled bet. ``net`` is derived per-row so surrender honors the
    configured ``surrender_multiplier`` (defaults to 0.5).

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
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
            )
        )
        row = cur.fetchone()
        if not row or int(row["hands_played"] or 0) == 0:
            return {}
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


def _stats_from_settled_games(
    args: Any, moniker: str, *, pool: Any = None,
) -> dict[str, Any]:
    """Aggregate stats for yahtzee / tictactoe from ``casino.__game``.

    Reads ``attrs->>'outcome'`` and ``attrs->>'bet_amount'`` written at
    settle. ``outcome`` is ``win`` / ``loss`` / ``draw``; ``net`` is
    stored verbatim from the settle path.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
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
            )
        )
        row = cur.fetchone()
        if not row or int(row["hands_played"] or 0) == 0:
            return {}
        return {
            "hands_played": int(row["hands_played"]),
            "wins": int(row["wins"]),
            "losses": int(row["losses"]),
            "draws": int(row["draws"]),
            "net": int(row["net"]),
        }


def _stats_from_poker_games(args: Any, moniker: str, *, pool: Any = None) -> dict[str, Any]:
    """Poker stats are not currently persisted to the DB.

    The poker service runs entirely in-memory
    (``casino.services.poker.PokerService._tables``); hand outcomes
    are awarded via ``winner.credits += table.pot`` and never written
    to ``casino.__game`` or ``casino.__betlog``. Returning ``{}``
    here reflects the actual measurement — there is no data to
    aggregate — rather than a fabricated ``hands_played: 0``. A real
    poker settlement path is a separate feature.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN, unused)
    """
    return {}


def get_table_stats(
    args: Any,
    moniker: str,
    game_type: str,
    surrender_multiplier: float = 0.5,
    *,
    pool: Any = None,
) -> dict[str, Any]:
    """Per-table aggregate stats, shape depends on ``game_type``.

    ``surrender_multiplier`` is forwarded to the blackjack aggregate
    only; ignored for other game types. Caller (typically
    ``services.table.TableService.get_table_stats``) reads it from
    the casino config block in ``bed.json`` so the per-table net
    stays consistent with what the settle path actually credited.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    if game_type == "slots":
        return _stats_from_slot_spins(args, moniker, pool=pool)
    if game_type == "blackjack":
        return _stats_from_blackjack_games(args, moniker, surrender_multiplier, pool=pool)
    if game_type in ("yahtzee", "tictactoe"):
        return _stats_from_settled_games(args, moniker, pool=pool)
    if game_type == "poker":
        return _stats_from_poker_games(args, moniker, pool=pool)
    return {}
