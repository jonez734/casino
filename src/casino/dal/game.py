# casino/dal/game.py
# Game data access layer
#
# All public functions in this module accept an optional ``pool`` keyword
# argument (CONN_POOL_PATTERN). When supplied, the function threads it into
# ``database.connect(args, pool=pool)`` so the caller owns the pool. When
# absent, the legacy ``database.connect(args)`` shape is used as a
# backward-compat fallback.

from typing import Any, Optional

from bbsengine6 import database
from bbsengine6.database import Jsonb


def _connect_ctx(args: Any, pool: Any):
    """CONN_POOL_PATTERN helper: pick connect(args, pool=pool) when pool
    is supplied, else fall back to ``database.connect(args)``.
    """
    if pool is None:
        return database.connect(args)
    return database.connect(args, pool=pool)


def create_game(args: Any, table_moniker: str, game_type: str, *, pool: Any = None) -> dict[str, Any]:
    """Create a new game instance at a table.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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


def get_active_game(args: Any, table_moniker: str, *, pool: Any = None) -> Optional[dict[str, Any]]:
    """Get the active game at a table.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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


def get_current_game(args: Any, table_moniker: str, *, pool: Any = None) -> Optional[dict[str, Any]]:
    """Get the most recent game at a table (including settled games).

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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


def update_game_status(args: Any, game_id: int, status: str, *, pool: Any = None) -> None:
    """Update game status.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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


def update_game_attrs(args: Any, game_id: int, attrs: dict[str, Any], *, pool: Any = None) -> None:
    """Merge attributes into a game's ``attrs`` JSONB column.

    Uses ``attrs || :attrs`` so existing keys are preserved. Caller
    is responsible for the key names (``outcome``, ``bet_amount``,
    ``net``, etc.) and for ensuring the values are JSONB-safe.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE $casino.__game SET attrs = attrs || :attrs WHERE id = :game_id",
                attrs=Jsonb(attrs), game_id=game_id,
            )
        )


def get_game_hands(args: Any, game_id: int, *, pool: Any = None) -> list[dict[str, Any]]:
    """Get all hands for a game.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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


def create_hand(args: Any, game_id: int, player_moniker: str, *, pool: Any = None) -> dict[str, Any]:
    """Create a new hand for a player in a game.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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


def update_hand_cards(args: Any, hand_id: int, cards: list[str], *, pool: Any = None) -> None:
    """Update hand with cards.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE $casino.__hand SET cards = :cards WHERE id = :hand_id",
                cards=Jsonb(cards), hand_id=hand_id
            )
        )


def update_hand_status(args: Any, hand_id: int, status: str, *, pool: Any = None) -> None:
    """Update hand status (e.g., 'bust', 'won', 'lost').

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE $casino.__hand SET attrs = attrs || :status WHERE id = :hand_id",
                status=Jsonb({"status": status}), hand_id=hand_id
            )
        )


def update_hand_attrs(args: Any, hand_id: int, attrs: dict[str, Any], *, pool: Any = None) -> None:
    """Update hand attributes.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE $casino.__hand SET attrs = :attrs WHERE id = :hand_id",
                attrs=Jsonb(attrs), hand_id=hand_id
            )
        )


def get_hand(args: Any, hand_id: int, *, pool: Any = None) -> Optional[dict[str, Any]]:
    """Get hand by ID.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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
    args: Any, game_id: int, player_moniker: str, *, pool: Any = None
) -> Optional[dict[str, Any]]:
    """Get player's hand in a game.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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
    args: Any, game_id: int, player_moniker: str, *, pool: Any = None
) -> list[dict[str, Any]]:
    """Get all hands for a player in a game (supports split hands).

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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


def get_dealer_hand(args: Any, game_id: int, *, pool: Any = None) -> Optional[dict[str, Any]]:
    """Get dealer's hand in a game.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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


def create_dealer_hand(args: Any, game_id: int, *, pool: Any = None) -> dict[str, Any]:
    """Create dealer's hand in a game.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
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


def update_dealer_hand_cards(args: Any, game_id: int, cards: list[str], *, pool: Any = None) -> None:
    """Update dealer's hand with cards.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "UPDATE $casino.__hand SET cards = :cards WHERE gameid = :game_id AND playermoniker = :dealer_moniker",
                cards=Jsonb(cards), game_id=game_id, dealer_moniker=DEALER_MONIKER
            )
        )


def get_dealer_hole_card(args: Any, game_id: int, *, pool: Any = None) -> Optional[str]:
    """Get dealer's hole card (face-down card).

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    dealer_hand = get_dealer_hand(args, game_id, pool=pool)
    if not dealer_hand:
        return None
    attrs = dealer_hand.get("attrs") or {}
    return attrs.get("hole_card")


def set_dealer_hole_card(args: Any, game_id: int, card: str, *, pool: Any = None) -> None:
    """Set dealer's hole card.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__hand SET attrs = jsonb_set(coalesce(attrs, '{}'::jsonb), '{hole_card}', to_jsonb(:card::text)) WHERE gameid = :game_id AND playermoniker = :dealer_moniker",
                    card=card, game_id=game_id, dealer_moniker=DEALER_MONIKER
                )
            )


def reveal_dealer_hole_card(args: Any, game_id: int, *, pool: Any = None) -> Optional[str]:
    """Reveal dealer's hole card (move to visible cards).

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    hole_card = get_dealer_hole_card(args, game_id, pool=pool)
    if not hole_card:
        return None

    dealer_hand = get_dealer_hand(args, game_id, pool=pool)
    if not dealer_hand:
        return None

    cards = list(dealer_hand["cards"]) if dealer_hand["cards"] else []
    if hole_card not in cards:
        cards.append(hole_card)

    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__hand SET cards = :cards, attrs = attrs - 'hole_card' WHERE gameid = :game_id AND playermoniker = :dealer_moniker",
                    cards=Jsonb(cards), game_id=game_id, dealer_moniker=DEALER_MONIKER
                )
            )

    return hole_card


def get_or_create_dealer_hand(args: Any, game_id: int, *, pool: Any = None) -> dict[str, Any]:
    """Get existing dealer hand or create new one.

    Args:
        pool: Optional connection pool (CONN_POOL_PATTERN)
    """
    hand = get_dealer_hand(args, game_id, pool=pool)
    if hand is None:
        hand = create_dealer_hand(args, game_id, pool=pool)
    return hand
