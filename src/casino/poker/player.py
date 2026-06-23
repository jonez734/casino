from typing import Any, List, Optional


class PokerPlayer:
    """Player in a poker game with associated state and actions."""

    def __init__(
        self,
        moniker: str,
        seat: int = 0,
        credits: int = 0,
    ):
        self.moniker: str = moniker
        self.seat: int = seat
        self.credits: int = credits
        self.hole_cards: List[str] = []
        self.current_bet: int = 0
        self.total_in_pot: int = 0
        self.has_acted: bool = False
        self.is_all_in: bool = False
        self.has_folded: bool = False
        self.showing_cards: bool = True

    def receive_card(self, card_str: str) -> None:
        """Receive a hole card.
        
        Args:
            card_str: Card in string format (e.g., 'AH', 'KD', '7S')
        """
        self.hole_cards.append(card_str)

    def receive_cards(self, cards: List[str]) -> None:
        """Receive multiple hole cards.
        
        Args:
            cards: List of card strings
        """
        self.hole_cards.extend(cards)

    def clear_hand(self) -> List[str]:
        """Clear the player's hand and return the cards.
        
        Returns:
            List of card strings that were in hand
        """
        old_cards = self.hole_cards.copy()
        self.hole_cards.clear()
        self.current_bet = 0
        self.total_in_pot = 0
        self.has_acted = False
        self.is_all_in = False
        self.has_folded = False
        self.showing_cards = True
        return old_cards

    def post_bet(self, amount: int) -> int:
        """Post a bet, deducting from credits.
        
        Args:
            amount: Amount to bet
            
        Returns:
            Actual amount bet (may be less than requested if all-in)
        """
        if amount >= self.credits:
            amount = self.credits
            self.is_all_in = True

        self.credits -= amount
        self.current_bet += amount
        self.total_in_pot += amount
        return amount

    def collect_winnings(self, amount: int) -> None:
        """Add winnings to player's credits.
        
        Args:
            amount: Amount to add to credits
        """
        self.credits += amount

    def can_act(self) -> bool:
        """Check if player can take an action.
        
        Returns:
            True if player can act (not folded, not all-in)
        """
        return not self.has_folded and not self.is_all_in

    def can_check(self, current_bet: int) -> bool:
        """Check if player can check.
        
        Args:
            current_bet: Current highest bet on the table
            
        Returns:
            True if player can check (no bet to call)
        """
        return self.can_act() and self.current_bet >= current_bet

    def can_call(self, current_bet: int) -> bool:
        """Check if player can call the current bet.
        
        Args:
            current_bet: Current highest bet on the table
            
        Returns:
            True if player can call (has enough credits)
        """
        if not self.can_act():
            return False
        call_amount = current_bet - self.current_bet
        return call_amount > 0 and call_amount <= self.credits

    def can_bet(self, min_bet: int) -> bool:
        """Check if player can bet.
        
        Args:
            min_bet: Minimum bet amount
            
        Returns:
            True if player has enough credits to bet
        """
        return self.can_act() and self.credits >= min_bet

    def get_call_amount(self, current_bet: int) -> int:
        """Get the amount needed to call.
        
        Args:
            current_bet: Current highest bet on the table
            
        Returns:
            Amount needed to call
        """
        return max(0, current_bet - self.current_bet)

    def get_bet_to_pot(self, current_bet: int) -> int:
        """Get total chips that would be in pot after calling.
        
        Args:
            current_bet: Current highest bet on the table
            
        Returns:
            Total chips in pot after calling
        """
        return self.total_in_pot + self.get_call_amount(current_bet)

    def get_visible_cards(self, opponent_moniker: str = "") -> List[str]:
        """Get cards visible to another player (for Stud variants).
        
        Args:
            opponent_moniker: The opponent viewing the cards (unused for hold'em)
            
        Returns:
            List of visible card strings (for hold'em, returns hole cards)
        """
        return self.hole_cards.copy()

    def is_showing_down(self) -> bool:
        """Check if player is in showdown (hasn't folded)."""
        return not self.has_folded

    def is_active(self) -> bool:
        """Check if player is still in the hand."""
        return not self.has_folded and not self.is_all_in

    def has_best_hand(self, other_players: List["PokerPlayer"]) -> bool:
        """Check if this player has the best hand against opponents.
        
        Note: This is a placeholder - actual comparison requires
        the evaluator from poker.variant.evaluator.
        
        Args:
            other_players: List of other active players
            
        Returns:
            True if player appears to win (placeholder)
        """
        return len(self.hole_cards) > 0 and self.is_active()

    def __repr__(self) -> str:
        return (
            f"PokerPlayer(moniker={self.moniker!r}, seat={self.seat}, "
            f"credits={self.credits}, hole_cards={len(self.hole_cards)}, "
            f"current_bet={self.current_bet}, folded={self.has_folded}, "
            f"all_in={self.is_all_in})"
        )

    def to_dict(self) -> dict:
        """Convert player to dictionary for serialization."""
        return {
            "moniker": self.moniker,
            "seat": self.seat,
            "credits": self.credits,
            "hole_cards": self.hole_cards.copy(),
            "current_bet": self.current_bet,
            "total_in_pot": self.total_in_pot,
            "has_acted": self.has_acted,
            "is_all_in": self.is_all_in,
            "has_folded": self.has_folded,
            "showing_cards": self.showing_cards,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PokerPlayer":
        """Create PokerPlayer from dictionary."""
        player = cls(
            moniker=data["moniker"],
            seat=data.get("seat", 0),
            credits=data.get("credits", 0),
        )
        player.hole_cards = data.get("hole_cards", [])
        player.current_bet = data.get("current_bet", 0)
        player.total_in_pot = data.get("total_in_pot", 0)
        player.has_acted = data.get("has_acted", False)
        player.is_all_in = data.get("is_all_in", False)
        player.has_folded = data.get("has_folded", False)
        player.showing_cards = data.get("showing_cards", True)
        return player
