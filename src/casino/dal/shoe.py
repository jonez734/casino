# casino/dal/shoe.py
# The shared shoe store. Blackjack and poker both keep their shoe here.
#
# A table's shoe is stored on its casino.__table row (shoe_cards, shoe_uses), so it survives a bed
# restart. Its reshuffle threshold is the table attribute ``shoe_threshold`` (default 0.8) and its
# deck count is ``shoe_decks`` (default 1).
#
# When casino runs with --audit, every draw, burn and reshuffle is also written to
# casino.__shoe_event (card, draw count, shoe size). Without --audit nothing is written there.

from __future__ import annotations

from typing import Any, Optional

from casino.dal import table as dal_table
from casino.shoe import DEFAULT_THRESHOLD, Shoe

DEFAULT_DECKS = 1


def _settings(table: dict[str, Any]) -> tuple[int, float]:
    attrs = table.get("attrs") or {}
    decks = int(attrs.get("shoe_decks", DEFAULT_DECKS) or DEFAULT_DECKS)
    threshold = float(attrs.get("shoe_threshold", DEFAULT_THRESHOLD) or DEFAULT_THRESHOLD)
    return decks, threshold


def load(args: Any, table_moniker: str, *, pool: Any = None) -> Shoe:
    """The table's shoe, restored from its row, or a new shuffled shoe if it has none yet."""
    table = dal_table.get_table(args, table_moniker, pool=pool)
    if not table:
        raise ValueError(f"Table {table_moniker} not found")
    decks, threshold = _settings(table)
    cards = table.get("shoe_cards") or []
    uses = int(table.get("shoe_uses") or 0)
    if not cards:
        shoe = Shoe(decks=decks, threshold=threshold)
        save(args, table_moniker, shoe, pool=pool)
        return shoe
    return Shoe.from_state(list(cards), uses, decks=decks, threshold=threshold)


def save(args: Any, table_moniker: str, shoe: Shoe, *, pool: Any = None) -> None:
    """Write the shoe's cards and draw count to the table row."""
    dal_table.update_shoe(args, table_moniker, shoe.cards, shoe.uses, pool=pool)


def audit_enabled(args: Any) -> bool:
    return bool(getattr(args, "audit", False))


def record_event(
    args: Any,
    table_moniker: str,
    *,
    kind: str,
    shoe: Shoe,
    card: Optional[str] = None,
    hand_id: Optional[int] = None,
    pool: Any = None,
) -> None:
    """Write one shoe event to casino.__shoe_event. A no-op unless casino runs with --audit."""
    if not audit_enabled(args):
        return
    if kind not in ("draw", "burn", "reshuffle"):
        raise ValueError(f"unknown shoe event kind {kind!r}")
    dal_table.insert_shoe_event(
        args,
        table_moniker,
        hand_id=hand_id,
        kind=kind,
        card=card,
        draw_count=shoe.uses,
        shoe_size=shoe.size,
        pool=pool,
    )
