# casino/dal/poker_state.py
# Persisted poker table state (casino.__poker_state). One jsonb document per table.
#
# The whole in-memory table is written after every action, so a bed restart resumes the game
# with the same seats, stacks, cards, bets, turn and shoe. On reload the turn clock is paused:
# the deadline is cleared, so a restart never costs a player their turn.

from __future__ import annotations

import json
from typing import Any, Optional

from casino.poker import get_variant
from casino.shoe import Shoe

FORMAT_VERSION = 1


def _player_to_dict(p: Any) -> dict[str, Any]:
    return {
        "moniker": p.moniker,
        "seat": p.seat,
        "credits": p.credits,
        "hole_cards": list(p.hole_cards),
        "current_bet": p.current_bet,
        "total_in_pot": p.total_in_pot,
        "has_acted": p.has_acted,
        "is_all_in": p.is_all_in,
        "has_folded": p.has_folded,
        "showing_cards": p.showing_cards,
    }


def _player_from_dict(d: dict[str, Any]) -> Any:
    from casino.poker.player import PokerPlayer

    p = PokerPlayer(moniker=d["moniker"], seat=d["seat"], credits=d["credits"])
    p.hole_cards = list(d.get("hole_cards", []))
    p.current_bet = d.get("current_bet", 0)
    p.total_in_pot = d.get("total_in_pot", 0)
    p.has_acted = d.get("has_acted", False)
    p.is_all_in = d.get("is_all_in", False)
    p.has_folded = d.get("has_folded", False)
    p.showing_cards = d.get("showing_cards", True)
    return p


def table_to_state(table: Any, shoe: Optional[Shoe]) -> dict[str, Any]:
    """The whole poker table as a JSON-safe document."""
    return {
        "format": FORMAT_VERSION,
        "moniker": table.moniker,
        "variant": table.variant.name,
        "betting_structure": int(table.betting_structure),
        "small_blind": table.small_blind,
        "big_blind": table.big_blind,
        "min_buy_in": table.min_buy_in,
        "max_buy_in": table.max_buy_in,
        "min_players": table.min_players,
        "max_players": table.max_players,
        "players": [_player_to_dict(p) for p in table.players.values()],
        "dealer_position": table.dealer_position,
        "current_street": table.current_street,
        "current_player": table.current_player,
        "turn_seconds": table.turn_seconds,
        "clock_penalty": table.clock_penalty,
        "current_bet": table.current_bet,
        "pot": table.pot,
        "community_cards": list(table.community_cards),
        "game_stage": table.game_stage,
        "last_aggressor": table.last_aggressor,
        "last_result": table.last_result,
        "shoe": None if shoe is None else {
            "decks": shoe.decks,
            "threshold": shoe.threshold,
            "cards": list(shoe.cards),
            "uses": shoe.uses,
            "reshuffles": shoe.reshuffles,
        },
    }


def state_to_table(doc: dict[str, Any]) -> tuple[Any, Optional[Shoe]]:
    """Rebuild a poker table and its shoe from a saved document. The turn clock is paused."""
    from casino.services.poker import PokerTableState

    if doc.get("format") != FORMAT_VERSION:
        raise ValueError(f"unsupported poker state format {doc.get('format')!r}")

    from casino.poker.lib import BettingStructure

    variant = get_variant(doc["variant"])
    variant.betting_structure = BettingStructure(doc["betting_structure"])
    table = PokerTableState(
        moniker=doc["moniker"],
        variant=variant,
        betting_structure=BettingStructure(doc["betting_structure"]),
        small_blind=doc["small_blind"],
        big_blind=doc["big_blind"],
        min_buy_in=doc["min_buy_in"],
        max_buy_in=doc["max_buy_in"],
        min_players=doc["min_players"],
        max_players=doc["max_players"],
    )
    for pd in doc.get("players", []):
        p = _player_from_dict(pd)
        table.players[p.moniker] = p
    table.dealer_position = doc.get("dealer_position", 0)
    table.current_street = doc.get("current_street", "preflop")
    table.current_player = doc.get("current_player")
    table.turn_seconds = doc.get("turn_seconds", 0)
    table.clock_penalty = doc.get("clock_penalty", "skip")
    table.turn_deadline = None  # paused: a restart never costs a player their turn
    table.current_bet = doc.get("current_bet", 0)
    table.pot = doc.get("pot", 0)
    table.community_cards = list(doc.get("community_cards", []))
    table.game_stage = doc.get("game_stage", "waiting")
    table.last_aggressor = doc.get("last_aggressor")
    table.last_result = doc.get("last_result")

    shoe = None
    sd = doc.get("shoe")
    if sd is not None:
        shoe = Shoe.from_state(sd["cards"], sd["uses"], decks=sd["decks"], threshold=sd["threshold"])
        shoe.reshuffles = sd.get("reshuffles", 0)
    return table, shoe


def dumps(table: Any, shoe: Optional[Shoe]) -> str:
    return json.dumps(table_to_state(table, shoe), default=str)


def load(args: Any, table_moniker: str, *, pool: Any = None) -> Optional[dict[str, Any]]:
    """The saved state document for a poker table, or None if it has none."""
    from bbsengine6 import database

    from casino.dal.table import _connect_ctx

    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "SELECT state FROM $casino.__poker_state WHERE tablemoniker = :moniker",
                moniker=table_moniker,
            )
        )
        row = cur.fetchone()
    if not row:
        return None
    state = row["state"]
    return json.loads(state) if isinstance(state, str) else state


def save(args: Any, table_moniker: str, table: Any, shoe: Optional[Shoe], *, pool: Any = None) -> None:
    """Upsert the whole table state. Called after every change to the table."""
    from bbsengine6 import database

    from casino.dal.table import _connect_ctx

    doc = json.dumps(table_to_state(table, shoe), default=str)
    with _connect_ctx(args, pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            database.query(
                "INSERT INTO $casino.__poker_state (tablemoniker, state, updated) "
                "VALUES (:moniker, :state, now()) "
                "ON CONFLICT (tablemoniker) DO UPDATE SET state = EXCLUDED.state, updated = now()",
                moniker=table_moniker, state=doc,
            )
        )
