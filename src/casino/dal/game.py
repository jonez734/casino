# casino/dal/game.py
# Game data access layer

from typing import Any, Dict, List, Optional

from bbsengine6 import database
from bbsengine6.database import Jsonb


def create_game(args: Any, table_id: int, game_type: str) -> Dict[str, Any]:
    """Create a new game instance at a table."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                """INSERT INTO casino.__game (casinoid, kind, status, datestarted)
                   VALUES (%s, %s, 'waiting', NOW())
                   RETURNING id, casinoid, kind, status, datestarted, dateended""",
                (table_id, game_type),
            )
            row = cur.fetchone()
            return {
                "id": row["id"],
                "casinoid": row["casinoid"],
                "kind": row["kind"],
                "status": row["status"],
                "datestarted": row["datestarted"],
                "dateended": row["dateended"],
            }


def get_active_game(args: Any, table_id: int) -> Optional[Dict[str, Any]]:
    """Get the active game at a table."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                """SELECT id, casinoid, kind, status, datestarted, dateended
                   FROM casino.__game 
                   WHERE casinoid = %s AND status NOT IN ('settled', 'cancelled')
                   ORDER BY datestarted DESC LIMIT 1""",
                (table_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "casinoid": row["casinoid"],
                    "kind": row["kind"],
                    "status": row["status"],
                    "datestarted": row["datestarted"],
                    "dateended": row["dateended"],
                }
            return None


def update_game_status(args: Any, game_id: int, status: str) -> None:
    """Update game status."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            if status in ("settled", "cancelled"):
                cur.execute(
                    "UPDATE casino.__game SET status = %s, dateended = NOW() WHERE id = %s",
                    (status, game_id),
                )
            else:
                cur.execute(
                    "UPDATE casino.__game SET status = %s WHERE id = %s",
                    (status, game_id),
                )


def get_game_hands(args: Any, game_id: int) -> List[Dict[str, Any]]:
    """Get all hands for a game."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                "SELECT id, gameid, playermoniker, cards, attrs FROM casino.__hand WHERE gameid = %s ORDER BY id",
                (game_id,),
            )
            hands = []
            for row in cur:
                hands.append(
                    {
                        "id": row["id"],
                        "gameid": row["gameid"],
                        "playermoniker": row["playermoniker"],
                        "cards": row["cards"] or [],
                        "attrs": row["attrs"] or {},
                    }
                )
            return hands


def create_hand(args: Any, game_id: int, player_moniker: str) -> Dict[str, Any]:
    """Create a new hand for a player in a game."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                """INSERT INTO casino.__hand (gameid, playermoniker, cards, attrs)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id, gameid, playermoniker, cards, attrs""",
                (game_id, player_moniker, [], Jsonb({})),
            )
            row = cur.fetchone()
            return {
                "id": row["id"],
                "gameid": row["gameid"],
                "playermoniker": row["playermoniker"],
                "cards": row["cards"],
                "attrs": row["attrs"],
            }


def update_hand_cards(args: Any, hand_id: int, cards: List[str]) -> None:
    """Update hand with cards."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                "UPDATE casino.__hand SET cards = %s WHERE id = %s",
                (Jsonb(cards), hand_id),
            )


def get_hand(args: Any, hand_id: int) -> Optional[Dict[str, Any]]:
    """Get hand by ID."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                "SELECT id, gameid, playermoniker, cards, attrs FROM casino.__hand WHERE id = %s",
                (hand_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "gameid": row["gameid"],
                    "playermoniker": row["playermoniker"],
                    "cards": row["cards"],
                    "attrs": row["attrs"],
                }
            return None


def get_player_hand(
    args: Any, game_id: int, player_moniker: str
) -> Optional[Dict[str, Any]]:
    """Get player's hand in a game."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                "SELECT id, gameid, playermoniker, cards, attrs FROM casino.__hand WHERE gameid = %s AND playermoniker = %s",
                (game_id, player_moniker),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "gameid": row["gameid"],
                    "playermoniker": row["playermoniker"],
                    "cards": row["cards"],
                    "attrs": row["attrs"],
                }
            return None


DEALER_MONIKER = "__dealer__"


def get_dealer_hand(args: Any, game_id: int) -> Optional[Dict[str, Any]]:
    """Get dealer's hand in a game."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                "SELECT id, gameid, playermoniker, cards, attrs FROM casino.__hand WHERE gameid = %s AND playermoniker = %s",
                (game_id, DEALER_MONIKER),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "gameid": row["gameid"],
                    "playermoniker": row["playermoniker"],
                    "cards": row["cards"] or [],
                    "attrs": row["attrs"] or {},
                }
            return None


def create_dealer_hand(args: Any, game_id: int) -> Dict[str, Any]:
    """Create dealer's hand in a game."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                """INSERT INTO casino.__hand (gameid, playermoniker, cards, attrs)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id, gameid, playermoniker, cards, attrs""",
                (game_id, DEALER_MONIKER, [], Jsonb({"is_dealer": True})),
            )
            row = cur.fetchone()
            return {
                "id": row["id"],
                "gameid": row["gameid"],
                "playermoniker": row["playermoniker"],
                "cards": row["cards"],
                "attrs": row["attrs"],
            }


def update_dealer_hand_cards(args: Any, game_id: int, cards: List[str]) -> None:
    """Update dealer's hand with cards."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                "UPDATE casino.__hand SET cards = %s WHERE gameid = %s AND playermoniker = %s",
                (Jsonb(cards), game_id, DEALER_MONIKER),
            )


def get_or_create_dealer_hand(args: Any, game_id: int) -> Dict[str, Any]:
    """Get existing dealer hand or create new one."""
    hand = get_dealer_hand(args, game_id)
    if hand is None:
        hand = create_dealer_hand(args, game_id)
    return hand
