"""Blackjack's event kinds, registered with its seam Domain (front-end-seam.md, section 5).

The application defines its own kinds (they are not generic message kinds). Registering them here lets
the Domain accept them; a kind not registered is refused.
"""

from __future__ import annotations

from bbsengine6.seam import domain as _domain
from bbsengine6.seam import events

BLACKJACK_KINDS = ("bet_placed", "card_dealt", "hand_settled", "round_expired")


def register_kinds(domain: _domain.Domain) -> None:
    """Register blackjack's kinds with ``domain``. Idempotent per domain."""
    for kind in BLACKJACK_KINDS:
        domain.register_kind(kind)


__all__ = ["BLACKJACK_KINDS", "register_kinds", "events"]
