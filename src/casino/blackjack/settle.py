# casino/blackjack/settle.py
# How a blackjack hand ends, shared by BED (services/game.py) and door mode (blackjack/play.py).
#
# Pure: no DB, no io. Callers pass card strings (e.g. "AH", "10S") and read the result.
#
# Terms follow table language:
#   natural blackjack  two-card 21 (an ace and a ten-value card)
#   blackjack          21 made with three or more cards
#
# Outcome values are the ones the stats and SQL already count: win, loss, push, bust, blackjack.
# Plus surrender and standup, which do not change win/loss/push stats.

from __future__ import annotations

from typing import Optional

_NATURAL_LABEL = "natural blackjack"


def _card_value(card: str) -> int:
    pips = card[:-1]
    if pips in ("J", "Q", "K"):
        return 10
    if pips == "A":
        return 11
    return int(pips)


def hand_total(cards: list[str]) -> int:
    """Best total: aces count 11 and drop to 1 as needed."""
    total = sum(_card_value(c) for c in cards)
    aces = sum(1 for c in cards if c[:-1] == "A")
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def is_natural(cards: list[str]) -> bool:
    return len(cards) == 2 and hand_total(cards) == 21


def classify_hand(
    player_cards: list[str],
    dealer_cards: list[str],
    *,
    player_status: Optional[str] = None,
) -> tuple[str, str]:
    """Return ``(outcome, reason)`` for a hand that was played out.

    ``player_status`` is the hand's stored status ("charlie" for a five-card Charlie). Naturals are
    checked first, so a natural always beats a non-natural 21 whatever the order of play.
    """
    player_total = hand_total(player_cards)
    dealer_total = hand_total(dealer_cards)
    player_nat = is_natural(player_cards)
    dealer_nat = is_natural(dealer_cards)

    if player_nat and dealer_nat:
        return "push", "both_natural"
    if dealer_nat:
        return "loss", "dealer_natural"
    if player_nat:
        return "blackjack", "player_natural"
    if player_total > 21:
        return "bust", "player_bust"
    if player_status == "charlie":
        return "win", "charlie"
    if dealer_total > 21:
        return "win", "dealer_bust"
    if player_total > dealer_total:
        return "win", "higher_total"
    if player_total < dealer_total:
        return "loss", "lower_total"
    return "push", "push_total"


def dealer_peek_applies(upcard: str) -> bool:
    """Standard peek rule: the dealer checks the hole card only when the upcard is an ace or a ten-value card,
    the only upcards that can make a natural."""
    pips = upcard[:-1]
    return pips in ("A", "10", "J", "Q", "K")


def dealer_peek_natural(dealer_cards: list[str]) -> bool:
    """True when the dealer's two cards are a natural (checked before any player action)."""
    return is_natural(dealer_cards)


def describe(
    reason: str,
    *,
    player_cards: list[str],
    dealer_cards: list[str],
    bet: int,
    net: int,
    returned: Optional[int] = None,
) -> str:
    """The one-line ending a player reads, e.g. ``dealer natural blackjack, bet 10, net -10``.

    ``reason`` is one of the classify_hand reasons, or ``surrender``, ``standup``, ``player_quit``.
    """
    player_total = hand_total(player_cards) if player_cards else 0
    dealer_total = hand_total(dealer_cards) if dealer_cards else 0

    if reason == "standup":
        return f"standup, bet {bet} refunded, net 0"
    if reason == "surrender":
        return f"surrendered, bet {bet}, returned {returned or 0}, net {_signed(net)}"

    heads = {
        "both_natural": "both natural blackjack",
        "dealer_natural": "dealer natural blackjack",
        "player_natural": "player natural blackjack",
        "player_bust": f"you busted with {player_total}",
        "dealer_bust": f"dealer busted with {dealer_total}",
        "charlie": "five-card Charlie",
        "higher_total": f"you {player_total}, dealer {dealer_total}",
        "lower_total": f"you {player_total}, dealer {dealer_total}",
        "push_total": f"push at {player_total}",
        "player_quit": "you quit the hand",
    }
    head = heads.get(reason, reason)
    return f"{head}, bet {bet}, net {_signed(net)}"


def _signed(net: int) -> str:
    """``+10``, ``-10``, or ``0`` (never ``+0``)."""
    if net == 0:
        return "0"
    return f"{net:+d}"
