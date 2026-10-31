"""Round clock for blackjack (simultaneous hands).

A round has one deadline covering every open hand. The deadline is stored on the round row
(casino.__game.action_deadline), so a reconnect sees the same time. When the deadline passes,
each unfinished hand takes the table's penalty:

- ``skip``: the hand stands on its current cards; the round settles as normal. No card is drawn.
- ``remove``: the hand is removed from the round and its bet is returned in full.

The clock is off when the table's turn_seconds is 0. Bots are clocked like humans. Expiry is applied by
the engine, not the client, and every expiry is written to the round log.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from bbsengine6 import database, io

PENALTIES = frozenset({"skip", "remove"})


def deadline_for(turn_seconds: int, *, now: Optional[datetime] = None) -> Optional[datetime]:
    """The round's action deadline, or None when the clock is off (turn_seconds 0)."""
    if not turn_seconds or turn_seconds <= 0:
        return None
    base = now or datetime.now(timezone.utc)
    return base + timedelta(seconds=int(turn_seconds))


def is_expired(deadline: Optional[datetime], *, now: Optional[datetime] = None) -> bool:
    """True when a deadline is set and has passed."""
    if deadline is None:
        return False
    current = now or datetime.now(timezone.utc)
    return current >= deadline


def penalty_for(table: dict[str, Any]) -> str:
    """The table's penalty; anything unknown falls back to skip (the default)."""
    value = (table or {}).get("clock_penalty") or "skip"
    return value if value in PENALTIES else "skip"


# Hand states that mean the seat has finished acting. Shared with GameService so the round and the
# clock agree on what "acted" means.
ACTED_STATUSES = ("standing", "surrendered", "bust", "charlie", "done", "split_1", "split_2", "standup")

# Hand status for a seat the round clock stood up from this round (see expire_round).
STANDUP_STATUS = "standup"


def is_bot_seat(seat: dict[str, Any]) -> bool:
    """True for a bot seat. Bots are clocked like humans; this only identifies the seat."""
    return bool(seat.get("is_bot"))


def log_expiry(args: Any, table_moniker: str, game_id: int, hand_id: Any, penalty: str,
               *, pool: Any = None, member_moniker: Optional[str] = None) -> None:
    """Record one expiry in the round log (casino.__log), as the tictactoe service does."""
    from bbsengine6 import database as _db

    message = f"round clock expired: penalty={penalty}"
    connect_cm = _db.connect(args, pool=pool) if pool is not None else _db.connect(args)
    with connect_cm as conn, _db.cursor(conn) as cur:
        cur.execute(
            _db.query(
                """INSERT INTO $casino.__log
                       (membermoniker, cardtablemoniker, gameid, datestamp, message, attrs)
                       VALUES (:member_moniker, :table_moniker, :game_id, NOW(), :message, :attrs)""",
                member_moniker=member_moniker,
                table_moniker=table_moniker,
                game_id=game_id,
                message=message,
                attrs=_db.Jsonb({"hand_id": hand_id, "penalty": penalty}),
            )
        )


def expire_round(game_service: Any, table_moniker: str, *, pool: Any = None) -> dict[str, Any]:
    """Apply the penalty to every unfinished hand in a round whose deadline has passed.

    The caller decides when the round is expired (is_expired on the stored deadline). For each
    pending hand: ``skip`` leaves the hand on its current cards so the round settles as normal;
    ``remove`` returns the bet in full and marks the hand so it is not settled. Each expiry is
    written to the round log. Returns a summary.
    """
    from casino.dal import game as dal_game
    from casino.dal import bet as dal_bet
    from casino.dal import table as dal_table

    args = game_service.args
    pool = pool or getattr(game_service, "_pool", None)
    game = dal_game.get_active_game(args, table_moniker, pool=pool)
    if not game:
        return {"success": False, "message": "No active game", "expired": 0}

    table = dal_table.get_table(args, table_moniker, pool=pool) or {}
    penalty = penalty_for(table)
    expired = 0
    for hand in dal_game.get_game_hands(args, game["id"], pool=pool):
        hand_id = hand.get("id")
        player = hand.get("playermoniker")
        if not hand_id or not player:
            continue
        # A seat that already acted is not late; only the seats still deciding are penalised.
        if (hand.get("attrs") or {}).get("status") in ACTED_STATUSES:
            continue
        bet = dal_bet.get_bet_for_hand(args, hand_id, pool=pool)
        if not bet or bet.get("status") != "pending":
            continue
        if penalty == "remove":
            # Standup: refund the stake in full and take the seat out of this round only. The seat
            # stays at the table and is dealt in the next round. Nothing is counted as a win, loss,
            # push, or hand played; settle_game records the seat as "standup".
            dal_bet.settle_bet(args, bet["id"], True, bet["amount"], pool=pool)
            dal_game.update_hand_status(args, hand_id, STANDUP_STATUS, pool=pool)
        # skip: nothing to change; the hand settles on its current cards with the round.
        log_expiry(args, table_moniker, game["id"], hand_id, penalty,
                   pool=pool, member_moniker=player)
        expired += 1

    if expired:
        game_service.settle_game(table_moniker)
    return {"success": True, "expired": expired, "penalty": penalty}
