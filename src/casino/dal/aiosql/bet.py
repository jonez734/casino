# casino/dal/aiosql/bet.py
# Async bet data access layer

from typing import Any, Dict, List, Optional

from bbsengine6 import database


async def place_bet(
    args: Any,
    player_moniker: str,
    table_moniker: str,
    game_id: int,
    amount: int,
    notes: Optional[str] = None,
    currenthand: Optional[str] = None,
) -> Dict[str, Any]:
    """Place a bet."""
    # Check which columns exist
    rows = await database.async_query(
        args,
        "SELECT column_name FROM information_schema.columns WHERE table_name = '__betlog'"
    )
    existing_cols = {r["column_name"] for r in rows}
    
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
    
    rows = await database.async_query(
        args,
        f"INSERT INTO $casino.__betlog ({col_str}) VALUES ({val_str}) RETURNING {', '.join(returning_cols)}",
        **params
    )
    row = rows[0]
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


async def settle_bet(
    args: Any,
    bet_id: int,
    won: bool,
    payout: int,
) -> Dict[str, Any]:
    """Settle a bet."""
    status = "won" if won else "lost"
    rows = await database.async_query(
        args,
        """UPDATE $casino.__betlog 
           SET status = :status 
           WHERE id = :bet_id 
           RETURNING id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted, notes, currenthand""",
        bet_id=bet_id, status=status
    )
    if rows:
        row = rows[0]
        return {
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
        }
    return {}


async def update_bet_notes(args: Any, bet_id: int, notes: str) -> None:
    """Update the notes for a bet."""
    await database.async_query(
        args,
        """UPDATE $casino.__betlog SET notes = :notes WHERE id = :bet_id""",
        notes=notes, bet_id=bet_id
    )


async def update_bet_currenthand(args: Any, bet_id: int, currenthand: str) -> None:
    """Update the currenthand for a bet."""
    # Check if currenthand column exists
    rows = await database.async_query(
        args,
        "SELECT 1 FROM information_schema.columns WHERE table_name = '__betlog' AND column_name = 'currenthand'"
    )
    if rows:
        await database.async_query(
            args,
            """UPDATE $casino.__betlog SET currenthand = :currenthand WHERE id = :bet_id""",
            currenthand=currenthand, bet_id=bet_id
        )


async def get_player_bets(args: Any, player_moniker: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get a player's bet history."""
    rows = await database.async_query(
        args,
        """SELECT id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted, notes, currenthand 
           FROM $casino.__betlog 
           WHERE playermoniker = :player_moniker 
           ORDER BY dateposted DESC LIMIT :limit""",
        player_moniker=player_moniker, limit=limit
    )
    return [
        {
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
        }
        for row in rows
    ]


async def get_table_bets(args: Any, game_id: int) -> List[Dict[str, Any]]:
    """Get all bets for a game."""
    rows = await database.async_query(
        args,
        """SELECT id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted, notes, currenthand, hand_id 
           FROM $casino.__betlog 
           WHERE gameid = :game_id 
           ORDER BY dateposted""",
        game_id=game_id
    )
    return [
        {
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
        }
        for row in rows
    ]


async def update_bet_hand_id(args: Any, bet_id: int, hand_id: int) -> None:
    """Link a bet to a specific hand."""
    await database.async_execute(
        args,
        "UPDATE $casino.__betlog SET hand_id = :hand_id WHERE id = :bet_id",
        hand_id=hand_id, bet_id=bet_id
    )


async def get_bet_for_hand(args: Any, hand_id: int) -> Optional[Dict[str, Any]]:
    """Get the bet associated with a specific hand."""
    rows = await database.async_query(
        args,
        """SELECT id, membermoniker, cardtablemoniker, gameid, playermoniker, amount, status, dateposted, hand_id 
           FROM $casino.__betlog 
           WHERE hand_id = :hand_id AND status = 'pending'""",
        hand_id=hand_id
    )
    if not rows:
        return None
    row = rows[0]
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
