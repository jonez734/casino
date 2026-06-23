from casino.poker.lib import BettingStructure, BetLimits
from casino.poker.variant.base import CommunityCardVariant
from casino.poker.variant import evaluator


class Omaha(CommunityCardVariant):
    name = "omaha"
    min_players = 2
    max_players = 10
    hole_cards_per_player = 4
    betting_structure = BettingStructure.POT_LIMIT

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
            "preflop": 4,  # Deal 4 hole cards in Omaha
        }

    def get_blinds(self) -> tuple[int, int]:
        return (1, 2)

    def evaluate_showdown(
        self, hole_cards: list[str], community_cards: list[str]
    ) -> tuple[int, list[str]]:
        """Evaluate best 5-card hand from hole + community.
        
        In Omaha, you MUST use exactly 2 hole cards + 3 community cards.
        """
        if len(hole_cards) < 2:
            return (0, [])
        
        rank, best_hand, used_hole = evaluator.evaluate_best_hand(
            hole_cards, community_cards, required_hole=2
        )
        return (rank, best_hand)

    def get_betting_limits(
        self, pot_size: int, current_bet: int, min_raise: int
    ) -> BetLimits:
        """Calculate betting limits for pot-limit Omaha."""
        if self.betting_structure == BettingStructure.NO_LIMIT:
            return BetLimits(
                min_raise=min_raise,
                max_raise=None,
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


class OmahaHiLo(Omaha):
    """Omaha Hi-Lo (8 or better) - split pot for low hand."""
    
    name = "omaha_hi_lo"
    
    def evaluate_showdown(
        self, hole_cards: list[str], community_cards: list[str]
    ) -> tuple[int, list[str]]:
        """Evaluate for hi-low split. Returns hi hand rank."""
        # TODO: Implement low hand evaluation (8 or better)
        return super().evaluate_showdown(hole_cards, community_cards)
