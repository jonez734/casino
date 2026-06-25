# casino/slots/player.py
# SlotPlayer - holds a player's credit balance, validates bets, records stats.

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .dealer import SlotDealer
from .lib import SpinResult


@dataclass
class SlotPlayer:
    """A single slot player. Knows its dealer, its credit balance, and how
    to validate bets against the table's min/max.
    """

    moniker: str
    credits: int
    dealer: SlotDealer
    min_bet: int = 1
    max_bet: int = 1000

    def __post_init__(self) -> None:
        if self.min_bet < 1:
            raise ValueError(f"min_bet must be >= 1, got {self.min_bet}")
        if self.max_bet < self.min_bet:
            raise ValueError(
                f"max_bet ({self.max_bet}) must be >= min_bet ({self.min_bet})"
            )
        if self.credits < 0:
            raise ValueError(f"credits must be >= 0, got {self.credits}")

    def validate_bet(self, bet: int) -> Optional[str]:
        """Return None if bet is valid, else a human-readable error."""
        if not isinstance(bet, int) or isinstance(bet, bool):
            return "Bet must be an integer"
        if bet <= 0:
            return "Bet must be positive"
        if bet < self.min_bet:
            return f"Bet {bet} is below table minimum {self.min_bet}"
        if bet > self.max_bet:
            return f"Bet {bet} exceeds table maximum {self.max_bet}"
        if bet > self.credits:
            return f"Insufficient credits ({self.credits}) for bet {bet}"
        return None

    def play(self, bet: int) -> SpinResult:
        """Validate the bet, debit credits, spin, credit payout, return the
        result. Caller is responsible for the bank transfer; this method
        only updates the in-memory ``credits`` field.
        """
        err = self.validate_bet(bet)
        if err is not None:
            raise ValueError(err)
        self.credits -= bet
        result = self.dealer.play(bet=bet)
        self.credits += result.payout
        return result
