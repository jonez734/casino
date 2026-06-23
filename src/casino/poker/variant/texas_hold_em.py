from casino.poker.lib import BettingStructure, BetLimits
from casino.poker.variant.base import CommunityCardVariant
from casino.poker.variant import evaluator


class TexasHoldEm(CommunityCardVariant):
    name = "texas_hold_em"
    min_players = 2
    max_players = 10
    hole_cards_per_player = 2
    betting_structure = BettingStructure.NO_LIMIT

    def get_betting_streets(self) -> list[str]:
        return ["preflop", "flop", "turn", "river"]

    def get_community_cards_per_street(self) -> dict[str, int]:
        return {
            "preflop": 0,
            "flop": 3,
            "turn": 1,
            "river": 1,
        }

    def get_street_before_deal(self) -> dict[str, int]:
        return {
            "preflop": 2,  # Deal 2 hole cards
        }

    def get_blinds(self) -> tuple[int, int]:
        return (1, 2)

    def evaluate_showdown(
        self, hole_cards: list[str], community_cards: list[str]
    ) -> tuple[int, list[str]]:
        """Evaluate best 5-card hand from hole + community."""
        rank, best_hand, _ = evaluator.evaluate_best_hand(hole_cards, community_cards)
        return (rank, best_hand)

    def get_betting_limits(
        self, pot_size: int, current_bet: int, min_raise: int
    ) -> BetLimits:
        """Calculate betting limits for no-limit hold'em."""
        if self.betting_structure == BettingStructure.NO_LIMIT:
            return BetLimits(
                min_raise=min_raise,
                max_raise=None,  # Unlimited
                min_bet=min_raise,
                max_bet=None,
            )
        elif self.betting_structure == BettingStructure.POT_LIMIT:
            max_raise = pot_size + current_bet
            return BetLimits(
                min_raise=min_raise,
                max_raise=max_raise,
                min_bet=min_raise,
                max_bet=max_raise,
            )
        else:  # Fixed limit
            return BetLimits(
                min_raise=min_raise,
                max_raise=min_raise * 4,
                min_bet=min_raise,
                max_bet=min_raise * 4,
            )
