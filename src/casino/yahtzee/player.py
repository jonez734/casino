# casino/yahtzee/player.py
# YahtzeePlayer - holds door-mode per-session state for one yahtzee game.
#
# Single-player in v1; the dealer is shared via YahtzeeDealer but dice
# state is per-player.

from __future__ import annotations

from . import lib as yahtzee_lib


class YahtzeePlayer:
    """A single yahtzee player. Tracks the per-session scorecard,
    dice, lock state, and rolls-left counter across the 13 rounds.
    """

    def __init__(
        self,
        moniker: str,
        credits: int,
        bet_amount: int,
        min_bet: int = yahtzee_lib.MIN_BET,
        max_bet: int = yahtzee_lib.MAX_BET,
    ) -> None:
        if min_bet < 1:
            raise ValueError(f"min_bet must be >= 1, got {min_bet}")
        if max_bet < min_bet:
            raise ValueError(
                f"max_bet ({max_bet}) must be >= min_bet ({min_bet})"
            )
        if credits < 0:
            raise ValueError(f"credits must be >= 0, got {credits}")
        if bet_amount < min_bet or bet_amount > min(credits, max_bet):
            raise ValueError(
                f"bet_amount ({bet_amount}) must be in "
                f"[{min_bet}, {min(credits, max_bet)}]"
            )

        self.moniker = moniker
        self.credits = credits
        self.bet_amount = bet_amount
        self.min_bet = min_bet
        self.max_bet = max_bet

        self.scorecard: dict[str, int | None] = {
            c: None for c in yahtzee_lib.CATEGORIES
        }
        self.round_idx = 0
        self.dice: tuple[int, ...] = (0, 0, 0, 0, 0)
        self.locked: list[bool] = [False] * 5
        self.rolls_left = 2
        self.last_score = 0
        self.is_over = False

    def grand_total(self) -> int:
        return yahtzee_lib.grand_total(self.scorecard)
