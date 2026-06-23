from casino.poker.lib import BettingStructure, BetLimits, HandRank
from casino.poker.variant.base import StudVariant
from casino.poker.variant import evaluator


class SevenCardStud(StudVariant):
    name = "seven_card_stud"
    min_players = 2
    max_players = 8
    hole_cards_per_player = 7
    betting_structure = BettingStructure.FIXED_LIMIT

    def get_betting_streets(self) -> list[str]:
        return ["third_street", "fourth_street", "fifth_street", "sixth_street", "seventh_street"]

    def get_community_cards_per_street(self) -> dict[str, int]:
        """7-Card Stud has no community cards."""
        return {
            "third_street": 0,
            "fourth_street": 0,
            "fifth_street": 0,
            "sixth_street": 0,
            "seventh_street": 0,
        }

    def get_street_before_deal(self) -> dict[str, int]:
        return {
            "third_street": 3,  # 2 down + 1 up
            "fourth_street": 1,
            "fifth_street": 1,
            "sixth_street": 1,
            "seventh_street": 1,
        }

    def get_blinds(self) -> tuple[int, int]:
        """Stud typically uses antes, not blinds. Return (ante, ante)."""
        return (1, 1)

    def evaluate_showdown(
        self, hole_cards: list[str], community_cards: list[str]
    ) -> tuple[int, list[str]]:
        """Evaluate best 5-card hand from 7 hole cards.
        
        7-Card Stud: use any 5 of the 7 cards.
        Community cards are empty for stud.
        """
        if len(hole_cards) < 5:
            return (0, [])
        
        rank, best_hand, _ = evaluator.evaluate_best_hand(hole_cards, [])
        return (rank, best_hand)

    def get_betting_limits(
        self, pot_size: int, current_bet: int, min_raise: int
    ) -> BetLimits:
        """Calculate betting limits for fixed-limit stud."""
        if self.betting_structure == BettingStructure.FIXED_LIMIT:
            # In fixed-limit stud, bet/raise is fixed on early streets,
            # doubles on later streets (river)
            return BetLimits(
                min_raise=min_raise,
                max_raise=min_raise,
                min_bet=min_raise,
                max_bet=min_raise,
            )
        elif self.betting_structure == BettingStructure.POT_LIMIT:
            max_raise = pot_size + current_bet
            return BetLimits(
                min_raise=min_raise,
                max_raise=max_raise,
                min_bet=min_raise,
                max_bet=max_raise,
            )
        else:
            return BetLimits(
                min_raise=min_raise,
                max_raise=None,
                min_bet=min_raise,
                max_bet=None,
            )
