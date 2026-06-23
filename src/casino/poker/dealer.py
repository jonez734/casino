import random
from typing import Any, List, Optional

from casino.poker.lib import PokerDeck, PokerCard


class PokerDealer:
    """Manages deck operations, shuffling, and dealing for poker games."""

    def __init__(self):
        self.deck: PokerDeck = PokerDeck()
        self.burn_cards: List[str] = []
        self.community_cards: List[str] = []

    def shuffle_deck(self, times: int = 1) -> None:
        """Shuffle the deck the specified number of times."""
        self.deck.shuffle(times)

    def deal_hole_cards(
        self, players: List[Any], count: int
    ) -> None:
        """Deal hole cards to all players.
        
        Args:
            players: List of objects with a receive_card() method or hole_cards list attribute
            count: Number of hole cards to deal to each player
        """
        for _ in range(count):
            for player in players:
                card = self.deal_card()
                if card:
                    self._give_card_to_player(player, card)

    def _give_card_to_player(self, player: Any, card: PokerCard) -> None:
        """Give a card to a player.
        
        Args:
            player: Player object (PokerPlayer or similar)
            card: Card to give
        """
        if hasattr(player, 'receive_card'):
            player.receive_card(card.to_string())
        elif hasattr(player, 'hole_cards'):
            player.hole_cards.append(card.to_string())

    def deal_community_cards(self, count: int) -> List[str]:
        """Deal community cards (the board).
        
        Args:
            count: Number of community cards to deal
            
        Returns:
            List of card strings dealing with
        """
        self.burn_card()  # Burn one card before dealing community cards
        
        cards = []
        for _ in range(count):
            card = self.deal_card()
            if card:
                cards.append(card.to_string())
                self.community_cards.append(card.to_string())
        
        return cards

    def burn_card(self) -> Optional[str]:
        """Burn the top card (called before community cards are dealt)."""
        burned = self.deck.burn(1)
        if burned:
            card_str = burned[0].to_string()
            self.burn_cards.append(card_str)
            return card_str
        return None

    def deal_card(self) -> Optional[PokerCard]:
        """Deal a single card from the deck."""
        cards = self.deck.deal(1)
        return cards[0] if cards else None

    def reset(self) -> None:
        """Reset the dealer for a new hand."""
        self.deck.reset()
        self.burn_cards.clear()
        self.community_cards.clear()

    def reset_community_cards(self) -> None:
        """Reset only community cards (keep deck state)."""
        self.burn_cards.clear()
        self.community_cards.clear()

    def remaining_cards(self) -> int:
        """Get the number of cards remaining in the deck."""
        return self.deck.remaining()

    def is_reshuffle_needed(self, threshold: float = 0.25) -> bool:
        """Check if the deck needs to be reshuffled.
        
        Args:
            threshold: Fraction of deck that must remain (default 25%)
            
        Returns:
            True if deck should be reshuffled
        """
        total_cards = 52
        remaining = self.deck.remaining()
        return remaining < (total_cards * threshold)

    def get_community_cards(self) -> List[str]:
        """Get current community cards."""
        return self.community_cards.copy()

    def get_burn_cards(self) -> List[str]:
        """Get burned cards."""
        return self.burn_cards.copy()

    def cut_deck(self, position: int = 52) -> None:
        """Cut the deck at a specific position (for extra randomization)."""
        if 0 < position < len(self.deck.cards):
            self.deck.cards = self.deck.cards[position:] + self.deck.cards[:position]
