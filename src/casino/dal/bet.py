# casino/dal/bet.py
# Bet data access layer
#
# All public functions in this module accept an optional ``pool`` keyword
# argument (CONN_POOL_PATTERN). When supplied, the function threads it into
# ``casino_conn.connect(args, pool=pool)`` so the caller owns the pool. When
# absent, the legacy ``casino_conn.connect(args)`` shape is used as a
# backward-compat fallback.

from typing import Any, Optional

from bbsengine6 import database
from casino.dal import conn as casino_conn


def _connect_ctx(args: Any, pool: Any):
    """Return a context manager for a database connection.

    CONN_POOL_PATTERN helper: when ``pool`` is supplied the connection is
    borrowed from the caller's pool; otherwise the legacy
    ``casino_conn.connect(args)`` fallback is used.
    """
    if pool is None:
        return casino_conn.connect(args)
    return casino_conn.connect(args, pool=pool)



def _resolve_bank_moniker(args: Any, name: str, *, pool: Any = None) -> str:
    """The bank account a name settles into: a table resolves to its mapped account (casino.__bank_table), a
    member's own name is already its account. A table with no mapping resolves to its own name (no account)."""
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "SELECT a.moniker FROM $casino.__bank_table t JOIN bank.__account a ON a.id = t.bank_account_id "
                "WHERE t.table_moniker = :name",
                name=name,
            )
        )
        row = cur.fetchone()
    return row["moniker"] if row else name


def _bank_move(args: Any, from_moniker: str, to_moniker: str, amount: int, kind: str, *, pool: Any = None,
               member_moniker: str = "", description: str = "") -> None:
    """Move ``amount`` from one bank account to another and record it. Raises ValueError if the source cannot pay.

    The debit is guarded in the same statement (``balance >= amount``), so the source can never overdraw, and the two
    balance changes and their transaction rows commit together.
    """
    from_moniker = _resolve_bank_moniker(args, from_moniker, pool=pool)
    to_moniker = _resolve_bank_moniker(args, to_moniker, pool=pool)
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE bank.__account SET balance = balance - :amount "
                "WHERE moniker = :from_moniker AND balance >= :amount RETURNING id",
                amount=amount, from_moniker=from_moniker,
            )
        )
        if cur.fetchone() is None:
            raise ValueError("Insufficient funds")
        cur.execute(
            database.query(
                "UPDATE bank.__account SET balance = balance + :amount WHERE moniker = :to_moniker",
                amount=amount, to_moniker=to_moniker,
            )
        )
        cur.execute(
            database.query(
                "INSERT INTO bank.__transaction (accountid, amount, transactiontype, description, membermoniker) "
                "SELECT id, :amount, :kind_debit, :description, :member FROM bank.__account WHERE moniker = :from_moniker",
                amount=amount, kind_debit=f"{kind}_debit", description=description, member=member_moniker,
                from_moniker=from_moniker,
            )
        )
        cur.execute(
            database.query(
                "INSERT INTO bank.__transaction (accountid, amount, transactiontype, description, membermoniker) "
                "SELECT id, :amount, :kind_credit, :description, :member FROM bank.__account WHERE moniker = :to_moniker",
                amount=amount, kind_credit=f"{kind}_credit", description=description, member=member_moniker,
                to_moniker=to_moniker,
            )
        )

def place_bet(
    args: Any,
    player_moniker: str,
    table_moniker: str,
    game_id: int,
    amount: int,
    notes: Optional[str] = None,
    currenthand: Optional[str] = None,
    *,
    pool: Any = None,
) -> dict[str, Any]:
    """
    Place a bet and deduct from player's balance.

    Args:
        args: Application args
        player_moniker: Player's BBS moniker
        table_moniker: Table moniker
        game_id: Game ID
        amount: Bet amount
        notes: Optional notes about the bet (for humans)
        currenthand: Optional current hand cards (for machines)
        pool: Optional connection pool (CONN_POOL_PATTERN)

    Returns:
        Bet dict with id, amount, etc.
    """
    # The stake moves from the player's bank account to the table's: the bank is the only money.
    _bank_move(args, player_moniker, table_moniker, amount, "bet", pool=pool,
               member_moniker=player_moniker, description=f"bet at {table_moniker}")
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:

            # Check which columns exist
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = '__betlog'"
            )
            existing_cols = {r["column_name"] for r in cur.fetchall()}

            # Build dynamic INSERT based on existing columns
            cols = ["membermoniker", "cardtablemoniker", "gameid", "playermoniker", "amount", "status", "dateposted"]
            vals = [":player_moniker", ":table_moniker", ":game_id", ":player_moniker2", ":amount", "'pending'", "NOW()"]
            params = {"player_moniker": player_moniker, "table_moniker": table_moniker, "game_id": game_id, "player_moniker2": player_moniker, "amount": amount}

            if "notes" in existing_cols:
                cols.append("notes")
                vals.append(":notes")
                params["notes"] = notes
            if "currenthand" in existing_cols:
                cols.append("currenthand")
                vals.append(":currenthand")
                params["currenthand"] = currenthand
            if "description" in existing_cols:
                cols.append("description")
                vals.append(":notes")
                params["notes"] = notes

            col_str = ", ".join(cols)
            val_str = ", ".join(vals)

            returning_cols = ["id", "membermoniker", "cardtablemoniker", "gameid", "playermoniker", "amount", "status", "dateposted"]

            cur.execute(
                database.query(
                    f"INSERT INTO $casino.__betlog ({col_str}) VALUES ({val_str}) RETURNING {', '.join(returning_cols)}",
                    **params
                )
            )
            row = cur.fetchone()
            return {
                "id": row["id"],
                "membermoniker": row["membermoniker"],
                "cardtablemoniker": row["cardtablemoniker"],
                "gameid": row["gameid"],
                "playermoniker": row["playermoniker"],
                "amount": row["amount"],
                "status": row["status"],
                "dateposted": row["dateposted"],
                "notes": notes,
                "currenthand": currenthand,
            }


def settle_bet(
    args: Any,
    bet_id: int,
    won: bool,
    payout: int,
    *,
    pool: Any = None,
    status: Optional[str] = None,
) -> None:
    """
    Settle a bet (win or loss).

    Args:
        bet_id: Bet ID
        won: Whether player won
        payout: Amount to pay out (including original bet for wins)
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "SELECT playermoniker, amount, cardtablemoniker FROM $casino.__betlog WHERE id = :bet_id",
                bet_id=bet_id
            )
        )
        row = cur.fetchone()
        if not row:
            return

        player_moniker = row["playermoniker"]
        table_moniker = row["cardtablemoniker"]

        # ``status`` names a push (or any other outcome) explicitly; otherwise it is won or lost.
        recorded = status or ("won" if won else "lost")
        cur.execute(
            database.query(
                "UPDATE $casino.__betlog SET status = :status WHERE id = :bet_id",
                status=recorded, bet_id=bet_id
            )
        )

        payout_to_move = payout if (won and payout > 0) else 0
    # The payout comes back out of the table's bank account to the player (the stake was already moved there).
    if payout_to_move > 0:
        _bank_move(args, table_moniker, player_moniker, payout_to_move, "payout", pool=pool,
                   member_moniker=player_moniker, description=f"payout from {table_moniker}")


def set_insurance(args: Any, bet_id: int, amount: int, *, pool: Any = None) -> None:
    """Set insurance bet amount for a bet.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__betlog SET attrs = jsonb_set(coalesce(attrs, '{}'::jsonb), '{insurance}', to_jsonb(:amount)) WHERE id = :bet_id",
                    amount=amount, bet_id=bet_id
                )
            )


def get_insurance(args: Any, bet_id: int, *, pool: Any = None) -> int:
    """Get insurance bet amount for a bet.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "SELECT attrs->'insurance' as insurance FROM $casino.__betlog WHERE id = :bet_id",
                bet_id=bet_id
            )
        )
        row = cur.fetchone()
        if row and row["insurance"]:
            return int(row["insurance"])
        return 0


def settle_insurance(args: Any, bet_id: int, won: bool, payout: int, *, pool: Any = None) -> None:
    """Settle insurance bet - add payout to player balance.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    if not won or payout <= 0:
        return

    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "SELECT playermoniker, cardtablemoniker FROM $casino.__betlog WHERE id = :bet_id",
                bet_id=bet_id
            )
        )
        row = cur.fetchone()
    if row:
        _bank_move(args, row["cardtablemoniker"], row["playermoniker"], payout, "insurance", pool=pool,
                   member_moniker=row["playermoniker"], description=f"insurance from {row['cardtablemoniker']}")


def update_bet_notes(args: Any, bet_id: int, notes: str, *, pool: Any = None) -> None:
    """Update the notes for a bet.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE $casino.__betlog SET notes = :notes WHERE id = :bet_id",
                notes=notes, bet_id=bet_id
            )
        )


def update_bet_currenthand(args: Any, bet_id: int, currenthand: str, *, pool: Any = None) -> None:
    """Update the currenthand for a bet.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        # Check if currenthand column exists
        cur.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = '__betlog' AND column_name = 'currenthand'"
        )
        if cur.fetchone():
            cur.execute(
                database.query(
                    "UPDATE $casino.__betlog SET currenthand = :currenthand WHERE id = :bet_id",
                    currenthand=currenthand, bet_id=bet_id
                )
            )


def get_player_bet_for_game(args: Any, game_id: int, player_moniker: str, *, pool: Any = None) -> Optional[dict[str, Any]]:
    """Get a player's bet for a specific game.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted FROM $casino.__betlog WHERE gameid = :game_id AND playermoniker = :player_moniker AND status = 'pending' ORDER BY dateposted DESC LIMIT 1",
                    game_id=game_id, player_moniker=player_moniker
                )
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "membermoniker": row["membermoniker"],
                "cardtablemoniker": row["cardtablemoniker"],
                "gameid": row["gameid"],
                "playermoniker": row["playermoniker"],
                "amount": row["amount"],
                "status": row["status"],
                "dateposted": row["dateposted"],
            }


def get_player_bets(args: Any, player_moniker: str, limit: int = 10, *, pool: Any = None) -> list[dict[str, Any]]:
    """Get player's recent bets.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted, notes, currenthand FROM $casino.__betlog WHERE playermoniker = :player_moniker ORDER BY dateposted DESC LIMIT :limit",
                    player_moniker=player_moniker, limit=limit
                )
            )
            bets = []
            for row in cur:
                bets.append({
                    "id": row["id"],
                    "membermoniker": row["membermoniker"],
                    "cardtablemoniker": row["cardtablemoniker"],
                    "gameid": row["gameid"],
                    "playermoniker": row["playermoniker"],
                    "amount": row["amount"],
                    "status": row["status"],
                    "dateposted": row["dateposted"],
                    "notes": row["notes"],
                    "currenthand": row["currenthand"],
                })
            return bets


def get_table_bets(args: Any, game_id: int, *, pool: Any = None) -> list[dict[str, Any]]:
    """Get all bets for a game.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted, notes, currenthand FROM $casino.__betlog WHERE gameid = :game_id ORDER BY dateposted",
                    game_id=game_id
                )
            )
            bets = []
            for row in cur:
                bets.append({
                    "id": row["id"],
                    "membermoniker": row["membermoniker"],
                    "cardtablemoniker": row["cardtablemoniker"],
                    "gameid": row["gameid"],
                    "playermoniker": row["playermoniker"],
                    "amount": row["amount"],
                    "status": row["status"],
                    "dateposted": row["dateposted"],
                    "notes": row["notes"],
                    "currenthand": row["currenthand"],
                })
            return bets


def place_split_bet(
    args: Any,
    player_moniker: str,
    table_moniker: str,
    game_id: int,
    amount: int,
    hand_id: Optional[int] = None,
    *,
    pool: Any = None,
) -> dict[str, Any]:
    """Place a bet for a split hand.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cols = ["membermoniker", "cardtablemoniker", "gameid", "playermoniker", "amount", "status", "dateposted"]
            vals = [":player_moniker", ":table_moniker", ":game_id", ":player_moniker2", ":amount", "'pending'", "NOW()"]
            params = {"player_moniker": player_moniker, "table_moniker": table_moniker, "game_id": game_id, "player_moniker2": player_moniker + "_split_2", "amount": amount}

            if hand_id is not None:
                cols.append("hand_id")
                vals.append(":hand_id")
                params["hand_id"] = hand_id

            col_str = ", ".join(cols)
            val_str = ", ".join(vals)

            returning_cols = ["id", "membermoniker", "cardtablemoniker", "gameid", "playermoniker", "amount", "status", "dateposted"]

            cur.execute(
                database.query(
                    f"INSERT INTO $casino.__betlog ({col_str}) VALUES ({val_str}) RETURNING {', '.join(returning_cols)}",
                    **params
                )
            )
            row = cur.fetchone()
            return {
                "id": row["id"],
                "membermoniker": row["membermoniker"],
                "cardtablemoniker": row["cardtablemoniker"],
                "gameid": row["gameid"],
                "playermoniker": row["playermoniker"],
                "amount": row["amount"],
                "status": row["status"],
                "dateposted": row["dateposted"],
            }


def double_bet(args: Any, bet_id: int, new_amount: int, *, pool: Any = None) -> None:
    """Update bet amount after doubling down.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE $casino.__betlog SET amount = :new_amount WHERE id = :bet_id",
                new_amount=new_amount, bet_id=bet_id
            )
        )


def update_bet_hand_id(args: Any, bet_id: int, hand_id: int, *, pool: Any = None) -> None:
    """Link a bet to a specific hand.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE $casino.__betlog SET hand_id = :hand_id WHERE id = :bet_id",
                hand_id=hand_id, bet_id=bet_id
            )
        )


def get_bet_for_hand(args: Any, hand_id: int, *, pool: Any = None) -> Optional[dict[str, Any]]:
    """Get the bet associated with a specific hand.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted, hand_id FROM $casino.__betlog WHERE hand_id = :hand_id AND status = 'pending'",
                    hand_id=hand_id
                )
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "membermoniker": row["membermoniker"],
                "cardtablemoniker": row["cardtablemoniker"],
                "gameid": row["gameid"],
                "playermoniker": row["playermoniker"],
                "amount": row["amount"],
                "status": row["status"],
                "dateposted": row["dateposted"],
                "hand_id": row["hand_id"],
            }


def get_hand_bets(args: Any, game_id: int, *, pool: Any = None) -> list[dict[str, Any]]:
    """Get all bets for a game with hand_id included.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted, notes, currenthand, hand_id FROM $casino.__betlog WHERE gameid = :game_id ORDER BY dateposted",
                    game_id=game_id
                )
            )
            bets = []
            for row in cur:
                bets.append({
                    "id": row["id"],
                    "membermoniker": row["membermoniker"],
                    "cardtablemoniker": row["cardtablemoniker"],
                    "gameid": row["gameid"],
                    "playermoniker": row["playermoniker"],
                    "amount": row["amount"],
                    "status": row["status"],
                    "dateposted": row["dateposted"],
                    "notes": row["notes"],
                    "currenthand": row["currenthand"],
                    "hand_id": row.get("hand_id"),
                })
            return bets
