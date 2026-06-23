import importlib.resources as resources
from dataclasses import dataclass
from typing import Literal, Optional

from ..lib import PACKAGENAME

Pips = Literal["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
Suit = Literal["H", "D", "S", "C"]


@dataclass
class Card:
    pips: Pips
    suit: Suit
    facedown: bool = False

    @classmethod
    def from_string(cls, card_str: str, facedown: bool = False) -> "Card":
        if len(card_str) == 2:
            pips, suit = card_str[0], card_str[1]
        elif len(card_str) == 3 and card_str.startswith("10"):
            pips, suit = "10", card_str[2]
        else:
            raise ValueError(f"Invalid card string: {card_str}")
        return cls(pips=pips, suit=suit, facedown=facedown)  # type: ignore[arg-type]

    def __str__(self) -> str:
        return f"{self.pips}{self.suit}"

    @property
    def value(self) -> int:
        if self.pips in ("J", "Q", "K"):
            return 10
        if self.pips == "A":
            return 11
        return int(self.pips)


# @since 20220810
# @see https://github.com/cirosantilli/python-sample-package-with-data/blob/master/python_sample_package_with_data/__init__.py
# @see https://stackoverflow.com/questions/3596979/manifest-in-ignored-on-python-setup-py-install-no-data-files-installed
# @see https://the-hitchhikers-guide-to-packaging.readthedocs.io/en/latest/quickstart.html
def get(card: str):
    (pips, suit) = card
    if suit == "D":
        suitname = "diamonds"
    elif suit == "H":
        suitname = "hearts"
    elif suit == "S":
        suitname = "spades"
    elif suit == "C":
        suitname = "clubs"
    else:
        raise ValueError(f"Invalid suit: {suit}")

    if pips == "A":
        short = "ace"
    elif pips == "J":
        short = "jack"
    elif pips == "Q":
        short = "queen"
    elif pips == "K":
        short = "king"
    else:
        short = pips

    name = f"{short}_of_{suitname}.png"
    return resources.open_binary(PACKAGENAME + ".cards", name)
