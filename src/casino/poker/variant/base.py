from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from casino.poker.lib import BettingStructure, BettingStreet


@dataclass
class BetLimits:
    min_raise: int
    max_raise: int | None  # None means unlimited (no-limit)
    min_bet: int
    max_bet: int | None


class BaseVariant(ABC):
    name: str
    min_players: int = 2
    max_players: int = 10
    hole_cards_per_player: int = 2
    betting_structure: BettingStructure = BettingStructure.NO_LIMIT

    @abstractmethod
    def get_betting_streets(self) -> list[str]:
        """Return list of betting street names."""
        pass

    @abstractmethod
    def get_community_cards_per_street(self) -> dict[str, int]:
        """Return dict mapping street name to number of community cards dealt."""
        pass

    @abstractmethod
    def get_street_before_deal(self) -> dict[str, int]:
        """Return dict mapping street name to number of cards dealt to players."""
        pass

    @abstractmethod
    def evaluate_showdown(
        self, hole_cards: list[str], community_cards: list[str]
    ) -> tuple[int, list[str]]:
        """Evaluate best hand and return (rank, best_5_cards)."""
        pass

    @abstractmethod
    def get_betting_limits(
        self, pot_size: int, current_bet: int, min_raise: int
    ) -> BetLimits:
        """Calculate betting limits based on current pot and bet."""
        pass

    def get_blinds(self) -> tuple[int, int]:
        """Return (small_blind, big_blind) amounts. Override for specific games."""
        return (1, 2)

    def get_max_community_cards(self) -> int:
        """Return total community cards for this variant."""
        return sum(self.get_community_cards_per_street().values())

    def get_total_hole_cards(self) -> int:
        """Return total hole cards dealt to each player."""
        return self.hole_cards_per_player

    def get_street_index(self, street_name: str) -> int:
        """Get index of a street by name."""
        streets = self.get_betting_streets()
        if street_name in streets:
            return streets.index(street_name)
        return -1

    def get_next_street(self, current_street: str) -> str | None:
        """Get the next street after current street."""
        streets = self.get_betting_streets()
        try:
            idx = streets.index(current_street)
            if idx + 1 < len(streets):
                return streets[idx + 1]
        except ValueError:
            pass
        return None


class CommunityCardVariant(BaseVariant):
    """Base class for variants that use community cards (Hold'em, Omaha)."""

    def get_street_before_deal(self) -> dict[str, int]:
        return {
            "preflop": self.hole_cards_per_player,
        }


class StudVariant(BaseVariant):
    """Base class for Stud variants (no community cards)."""

    def get_street_before_deal(self) -> dict[str, int]:
        return {
            "third_street": 2,  # 2 down cards initially
            "fourth_street": 1,
            "fifth_street": 1,
            "sixth_street": 1,
            "seventh_street": 1,
        }
