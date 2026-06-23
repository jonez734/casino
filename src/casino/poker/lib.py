import random
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Optional


SUITS = ["hearts", "diamonds", "clubs", "spades"]
SUIT_SYMBOLS = {"hearts": "{u:heart}", "diamonds": "{u:diamond}", "clubs": "{u:club}", "spades": "{u:spade}"}
SUIT_CHARS = {"hearts": "H", "diamonds": "D", "clubs": "C", "spades": "S"}

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_ORDER = {rank: i for i, rank in enumerate(RANKS)}


class HandRank(IntEnum):
    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    ROYAL_FLUSH = 9


class BettingStructure(IntEnum):
    NO_LIMIT = 0
    POT_LIMIT = 1
    FIXED_LIMIT = 2


class BettingStreet(IntEnum):
    PREFLOP = 0
    FLOP = 1
    TURN = 2
    RIVER = 3
    THIRD_STREET = 4
    FOURTH_STREET = 5
    FIFTH_STREET = 6
    SIXTH_STREET = 7
    SEVENTH_STREET = 8


@dataclass
class BetLimits:
    min_raise: int
    max_raise: Optional[int]
    min_bet: int
    max_bet: Optional[int]


class PokerCard:
    def __init__(self, rank: str, suit: str, facedown: bool = False):
        self.rank = rank
        self.suit = suit
        self.facedown = facedown

    def __repr__(self):
        return f"PokerCard({self.rank}{self.suit})"

    def __str__(self):
        symbol = SUIT_SYMBOLS.get(self.suit, "")
        return f"{self.rank}{symbol}"

    @property
    def rank_value(self) -> int:
        return RANK_ORDER.get(self.rank, 0)

    @property
    def is_ace(self) -> bool:
        return self.rank == "A"

    @classmethod
    def from_string(cls, s: str, facedown: bool = False) -> "PokerCard":
        if len(s) < 2:
            raise ValueError(f"Invalid card string: {s}")
        rank = s[:-1] if s[:-1] == "10" else s[0]
        suit_char = s[-1]
        suit = next((k for k, v in SUIT_CHARS.items() if v == suit_char), "hearts")
        return cls(rank, suit, facedown)

    def to_string(self) -> str:
        suit_char = SUIT_CHARS.get(self.suit, "H")
        return f"{self.rank}{suit_char}"


class PokerDeck:
    def __init__(self):
        self.cards: list[PokerCard] = []
        self.burn_pile: list[PokerCard] = []
        self._build()

    def _build(self):
        self.cards = []
        for suit in SUITS:
            for rank in RANKS:
                self.cards.append(PokerCard(rank, suit))
        self.burn_pile = []

    def shuffle(self, times: int = 1):
        for _ in range(times):
            random.shuffle(self.cards)

    def deal(self, count: int = 1) -> list[PokerCard]:
        cards = []
        for _ in range(count):
            if self.cards:
                cards.append(self.cards.pop())
        return cards

    def burn(self, count: int = 1) -> list[PokerCard]:
        burned = []
        for _ in range(count):
            if self.cards:
                burned.append(self.cards.pop())
        self.burn_pile.extend(burned)
        return burned

    def remaining(self) -> int:
        return len(self.cards)

    def reset(self):
        self._build()


def get_suit_symbol(suit: str) -> str:
    return SUIT_SYMBOLS.get(suit, "")


def get_rank_order(rank: str) -> int:
    return RANK_ORDER.get(rank, 0)


def parse_card_string(card_str: str, facedown: bool = False) -> PokerCard:
    return PokerCard.from_string(card_str, facedown)
