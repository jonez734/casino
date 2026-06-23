from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class GameType(str, Enum):
    BLACKJACK = "blackjack"
    POKER = "poker"
    SLOTS = "slots"
    YAHTZEE = "yahtzee"


class GameAction(str, Enum):
    BET = "bet"
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"
    FOLD = "fold"
    ALLIN = "allin"
    SPIN = "spin"
    ROLL = "roll"
    LOCK = "lock"


GAME_ACTIONS: dict[GameType, list[GameAction]] = {
    GameType.BLACKJACK: [GameAction.BET, GameAction.HIT, GameAction.STAND, GameAction.DOUBLE, GameAction.SPLIT],
    GameType.POKER: [GameAction.CHECK, GameAction.CALL, GameAction.RAISE, GameAction.FOLD, GameAction.ALLIN],
    GameType.SLOTS: [GameAction.SPIN],
    GameType.YAHTZEE: [GameAction.ROLL, GameAction.LOCK],
}


def get_actions_for_game(game_type: str | GameType) -> list[str]:
    """Get list of available actions for a game type."""
    if isinstance(game_type, str):
        try:
            game_type = GameType(game_type)
        except ValueError:
            return []
    return [action.value for action in GAME_ACTIONS.get(game_type, [])]


class BaseGame(ABC):
    """Base class for casino games."""

    def __init__(self, table_id: int, **kwargs: Any):
        self.table_id = table_id
        self.game_type: GameType
        self.min_bet: int = kwargs.get("min_bet", 1)
        self.max_bet: int = kwargs.get("max_bet", 1000)

    @abstractmethod
    def get_available_actions(self, player_id: int) -> list[str]:
        """Return list of available actions for a player."""
        pass

    @abstractmethod
    def process_action(self, player_id: int, action: str, **kwargs: Any) -> dict:
        """Process a player action and return new game state."""
        pass

    @abstractmethod
    def get_state(self) -> dict:
        """Return current game state."""
        pass

    @abstractmethod
    def is_game_over(self) -> bool:
        """Check if the current round is over."""
        pass

    def reset(self) -> None:
        """Reset the game for a new round."""
        pass
