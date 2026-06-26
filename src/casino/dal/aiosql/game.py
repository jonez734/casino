# casino/dal/async/game.py
# Async game data access layer

from typing import Any, Dict, List, Optional

from bbsengine6 import database


async def create_game(args: Any, table_moniker: str, game_type: str) -> Dict[str, Any]:
    """Create a new game instance at a table."""
    rows = await database.async_query(
        args,
        """INSERT INTO $casino.__game (tablemoniker, kind, status, datestarted) 
           VALUES (:table_moniker, :kind, 'waiting', NOW()) 
           RETURNING id, tablemoniker, kind, status, datestarted, dateended""",
        table_moniker=table_moniker, kind=game_type
    )
    row = rows[0]
    return {
        "id": row["id"],
        "tablemoniker": row["tablemoniker"],
        "kind": row["kind"],
        "status": row["status"],
        "datestarted": row["datestarted"],
        "dateended": row["dateended"],
    }


async def get_active_game(args: Any, table_moniker: str) -> Optional[Dict[str, Any]]:
    """Get the active game at a table."""
    rows = await database.async_query(
        args,
        """SELECT id, tablemoniker, kind, status, datestarted, dateended 
           FROM $casino.__game 
           WHERE tablemoniker = :table_moniker AND status NOT IN ('settled', 'cancelled') 
           ORDER BY datestarted DESC LIMIT 1""",
        table_moniker=table_moniker
    )
    if rows:
        row = rows[0]
        return {
            "id": row["id"],
            "tablemoniker": row["tablemoniker"],
            "kind": row["kind"],
            "status": row["status"],
            "datestarted": row["datestarted"],
            "dateended": row["dateended"],
        }
    return None


async def get_current_game(args: Any, table_moniker: str) -> Optional[Dict[str, Any]]:
    """Get the most recent game at a table (including settled games)."""
    rows = await database.async_query(
        args,
        """SELECT id, tablemoniker, kind, status, datestarted, dateended 
           FROM $casino.__game 
           WHERE tablemoniker = :table_moniker 
           ORDER BY datestarted DESC LIMIT 1""",
        table_moniker=table_moniker
    )
    if rows:
        row = rows[0]
        return {
            "id": row["id"],
            "tablemoniker": row["tablemoniker"],
            "kind": row["kind"],
            "status": row["status"],
            "datestarted": row["datestarted"],
            "dateended": row["dateended"],
        }
    return None


async def update_game_status(args: Any, game_id: int, status: str) -> None:
    """Update game status."""
    await database.async_query(
        args,
        "UPDATE $casino.__game SET status = :status WHERE id = :game_id",
        game_id=game_id, status=status
    )


async def get_game_hands(args: Any, game_id: int) -> List[Dict[str, Any]]:
    """Get all hands for a game."""
    rows = await database.async_query(
        args,
        """SELECT id, gameid, playermoniker, cards, attrs 
           FROM $casino.__hand WHERE gameid = :game_id""",
        game_id=game_id
    )
    return [
        {
            "id": row["id"],
            "gameid": row["gameid"],
            "playermoniker": row["playermoniker"],
            "cards": row["cards"] or [],
            "attrs": row["attrs"] or {},
        }
        for row in rows
    ]


async def create_hand(args: Any, game_id: int, player_moniker: str) -> Dict[str, Any]:
    """Create a new hand for a player."""
    rows = await database.async_query(
        args,
        """INSERT INTO $casino.__hand (gameid, playermoniker, cards, attrs) 
           VALUES (:game_id, :player_moniker, '[]'::jsonb, '{}'::jsonb) 
           RETURNING id, gameid, playermoniker, cards, attrs""",
        game_id=game_id, player_moniker=player_moniker
    )
    row = rows[0]
    return {
        "id": row["id"],
        "gameid": row["gameid"],
        "playermoniker": row["playermoniker"],
        "cards": row["cards"] or [],
        "attrs": row["attrs"] or {},
    }


async def update_hand_cards(args: Any, hand_id: int, cards: List[str]) -> None:
    """Update hand cards."""
    await database.async_query(
        args,
        "UPDATE $casino.__hand SET cards = :cards WHERE id = :hand_id",
        hand_id=hand_id, cards=cards
    )


async def update_hand_status(args: Any, hand_id: int, status: str) -> None:
    """Update hand status."""
    await database.async_query(
        args,
        "UPDATE $casino.__hand SET attrs = jsonb_set(coalesce(attrs, '{}'::jsonb), '{status}', to_jsonb(:status)) WHERE id = :hand_id",
        hand_id=hand_id, status=status
    )


async def get_hand(args: Any, hand_id: int) -> Optional[Dict[str, Any]]:
    """Get a hand by ID."""
    rows = await database.async_query(
        args,
        "SELECT id, gameid, playermoniker, cards, attrs FROM $casino.__hand WHERE id = :hand_id",
        hand_id=hand_id
    )
    if rows:
        row = rows[0]
        return {
            "id": row["id"],
            "gameid": row["gameid"],
            "playermoniker": row["playermoniker"],
            "cards": row["cards"] or [],
            "attrs": row["attrs"] or {},
        }
    return None


async def get_player_hand(args: Any, game_id: int, player_moniker: str) -> Optional[Dict[str, Any]]:
    """Get a player's hand in a game."""
    rows = await database.async_query(
        args,
        """SELECT id, gameid, playermoniker, cards, attrs 
           FROM $casino.__hand 
           WHERE gameid = :game_id AND playermoniker = :player_moniker""",
        game_id=game_id, player_moniker=player_moniker
    )
    if rows:
        row = rows[0]
        return {
            "id": row["id"],
            "gameid": row["gameid"],
            "playermoniker": row["playermoniker"],
            "cards": row["cards"] or [],
            "attrs": row["attrs"] or {},
        }
    return None


async def get_dealer_hand(args: Any, game_id: int) -> Optional[Dict[str, Any]]:
    """Get dealer's hand in a game."""
    rows = await database.async_query(
        args,
        """SELECT id, gameid, playermoniker, cards, attrs 
           FROM $casino.__hand 
           WHERE gameid = :game_id AND playermoniker = 'dealer'""",
        game_id=game_id
    )
    if rows:
        row = rows[0]
        return {
            "id": row["id"],
            "gameid": row["gameid"],
            "playermoniker": row["playermoniker"],
            "cards": row["cards"] or [],
            "attrs": row["attrs"] or {},
        }
    return None


async def create_dealer_hand(args: Any, game_id: int) -> Dict[str, Any]:
    """Create dealer's hand in a game."""
    rows = await database.async_query(
        args,
        """INSERT INTO $casino.__hand (gameid, playermoniker, cards, attrs) 
           VALUES (:game_id, 'dealer', '[]'::jsonb, '{}'::jsonb) 
           RETURNING id, gameid, playermoniker, cards, attrs""",
        game_id=game_id
    )
    row = rows[0]
    return {
        "id": row["id"],
        "gameid": row["gameid"],
        "playermoniker": row["playermoniker"],
        "cards": row["cards"] or [],
        "attrs": row["attrs"] or {},
    }


async def update_dealer_hand_cards(args: Any, game_id: int, cards: List[str]) -> None:
    """Update dealer's hand cards."""
    await database.async_query(
        args,
        """UPDATE $casino.__hand 
           SET cards = :cards 
           WHERE gameid = :game_id AND playermoniker = 'dealer'""",
        game_id=game_id, cards=cards
    )


async def get_or_create_dealer_hand(args: Any, game_id: int) -> Dict[str, Any]:
    """Get or create dealer's hand."""
    hand = await get_dealer_hand(args, game_id)
    if hand:
        return hand
    return await create_dealer_hand(args, game_id)
