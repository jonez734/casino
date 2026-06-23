from dataclasses import dataclass, field
from typing import List, Optional

from casino.cards import Card


@dataclass
class Hand:
    cards: List[Card] = field(default_factory=list)
    is_split: bool = False

    def total(self) -> int:
        total = sum(c.value for c in self.cards)
        aces = sum(1 for c in self.cards if c.pips == "A")
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        return total

    def is_bust(self) -> bool:
        return self.total() > 21

    def is_blackjack(self) -> bool:
        return len(self.cards) == 2 and self.total() == 21

    def is_natural(self) -> bool:
        return self.is_blackjack()

    def is_split_hand(self) -> bool:
        return self.is_split

    def can_split(self) -> bool:
        if len(self.cards) != 2:
            return False
        return self.cards[0].pips == self.cards[1].pips

    def can_double_down(self) -> bool:
        return len(self.cards) == 2

    @classmethod
    def from_strings(cls, card_strings: List[str], is_split: bool = False) -> "Hand":
        cards = [Card.from_string(s) for s in card_strings]
        return cls(cards=cards, is_split=is_split)

    def to_strings(self) -> List[str]:
        return [str(c) for c in self.cards]
