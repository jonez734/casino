# casino/dal/game.py
# Game data access layer

from typing import Any, Dict, List, Optional

from bbsengine6 import database
from bbsengine6.database import Jsonb


def create_game(args: Any, table_moniker: str, game_type: str) -> Dict[str, Any]:
    """Create a new game instance at a table."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "INSERT INTO $casino.__game (tablemoniker, kind, status, datestarted) VALUES (:table_moniker, :kind, 'waiting', NOW()) RETURNING id, tablemoniker, kind, status, datestarted, dateended",
                    table_moniker=table_moniker, kind=game_type
                )
            )
            row = cur.fetchone()
            return {
                "id": row["id"],
                "tablemoniker": row["tablemoniker"],
                "kind": row["kind"],
                "status": row["status"],
                "datestarted": row["datestarted"],
                "dateended": row["dateended"],
            }


def get_active_game(args: Any, table_moniker: str) -> Optional[Dict[str, Any]]:
    """Get the active game at a table."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, tablemoniker, kind, status, datestarted, dateended FROM $casino.__game WHERE tablemoniker = :table_moniker AND status NOT IN ('settled', 'cancelled') ORDER BY datestarted DESC LIMIT 1",
                    table_moniker=table_moniker
                )
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "tablemoniker": row["tablemoniker"],
                    "kind": row["kind"],
                    "status": row["status"],
                    "datestarted": row["datestarted"],
                    "dateended": row["dateended"],
                }
            return None


def get_current_game(args: Any, table_moniker: str) -> Optional[Dict[str, Any]]:
    """Get the most recent game at a table (including settled games)."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, tablemoniker, kind, status, datestarted, dateended FROM $casino.__game WHERE tablemoniker = :table_moniker ORDER BY datestarted DESC LIMIT 1",
                    table_moniker=table_moniker
                )
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "tablemoniker": row["tablemoniker"],
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
                    database.query(
                        "UPDATE $casino.__game SET status = :status, dateended = NOW() WHERE id = :game_id",
                        status=status, game_id=game_id
                    )
                )
            else:
                cur.execute(
                    database.query(
                        "UPDATE $casino.__game SET status = :status WHERE id = :game_id",
                        status=status, game_id=game_id
                    )
                )


def get_game_hands(args: Any, game_id: int) -> List[Dict[str, Any]]:
    """Get all hands for a game."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, gameid, playermoniker, cards, attrs FROM $casino.__hand WHERE gameid = :game_id ORDER BY id",
                    game_id=game_id
                )
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
                database.query(
                    "INSERT INTO $casino.__hand (gameid, playermoniker, cards, attrs) VALUES (:game_id, :player_moniker, :cards, :attrs) RETURNING id, gameid, playermoniker, cards, attrs",
                    game_id=game_id, player_moniker=player_moniker, cards=[], attrs=Jsonb({})
                )
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
                database.query(
                    "UPDATE $casino.__hand SET cards = :cards WHERE id = :hand_id",
                    cards=Jsonb(cards), hand_id=hand_id
                )
            )


def update_hand_status(args: Any, hand_id: int, status: str) -> None:
    """Update hand status (e.g., 'bust', 'won', 'lost')."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__hand SET attrs = attrs || :status WHERE id = :hand_id",
                    status=Jsonb({"status": status}), hand_id=hand_id
                )
            )


def update_hand_attrs(args: Any, hand_id: int, attrs: Dict[str, Any]) -> None:
    """Update hand attributes."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__hand SET attrs = :attrs WHERE id = :hand_id",
                    attrs=Jsonb(attrs), hand_id=hand_id
                )
            )


def get_hand(args: Any, hand_id: int) -> Optional[Dict[str, Any]]:
    """Get hand by ID."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, gameid, playermoniker, cards, attrs FROM $casino.__hand WHERE id = :hand_id",
                    hand_id=hand_id
                )
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
                database.query(
                    "SELECT id, gameid, playermoniker, cards, attrs FROM $casino.__hand WHERE gameid = :game_id AND playermoniker = :player_moniker",
                    game_id=game_id, player_moniker=player_moniker
                )
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


def get_player_hands(
    args: Any, game_id: int, player_moniker: str
) -> List[Dict[str, Any]]:
    """Get all hands for a player in a game (supports split hands)."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, gameid, playermoniker, cards, attrs FROM $casino.__hand WHERE gameid = :game_id AND (playermoniker = :player_moniker OR playermoniker LIKE :split_pattern) ORDER BY id",
                    game_id=game_id, player_moniker=player_moniker, split_pattern=player_moniker + "_split_%"
                )
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


DEALER_MONIKER = "__dealer__"


def get_dealer_hand(args: Any, game_id: int) -> Optional[Dict[str, Any]]:
    """Get dealer's hand in a game."""
    with database.connect(args) as conn:
        with database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT id, gameid, playermoniker, cards, attrs FROM $casino.__hand WHERE gameid = :game_id AND playermoniker = :dealer_moniker",
                    game_id=game_id, dealer_moniker=DEALER_MONIKER
                )
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
                database.query(
                    "INSERT INTO $casino.__hand (gameid, playermoniker, cards, attrs) VALUES (:game_id, :dealer_moniker, :cards, :attrs) RETURNING id, gameid, playermoniker, cards, attrs",
                    game_id=game_id, dealer_moniker=DEALER_MONIKER, cards=[], attrs=Jsonb({"is_dealer": True})
                )
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
                database.query(
                    "UPDATE $casino.__hand SET cards = :cards WHERE gameid = :game_id AND playermoniker = :dealer_moniker",
                    cards=Jsonb(cards), game_id=game_id, dealer_moniker=DEALER_MONIKER
                )
            )


def get_or_create_dealer_hand(args: Any, game_id: int) -> Dict[str, Any]:
    """Get existing dealer hand or create new one."""
    hand = get_dealer_hand(args, game_id)
    if hand is None:
        hand = create_dealer_hand(args, game_id)
    return hand
