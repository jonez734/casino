"""
casino/games/base.py
Backwards-compatible shim.

The game-type catalog (``GameType``, ``GameAction``, ``GAME_ACTIONS``,
``get_actions_for_game``, ``BaseGame``) was moved to
``bbsengine6.games.base`` so the menu-derivation helper in
``bbsengine6.games.menu`` could depend on a bbsengine6-owned catalog
without circular imports. This file re-exports the same symbols so
any legacy ``from casino.games.base import ...`` path keeps working.
"""

from bbsengine6.games.base import (
    GAME_ACTIONS,
    BaseGame,
    GameAction,
    GameType,
    get_actions_for_game,
)

__all__ = [
    "BaseGame",
    "GameType",
    "GameAction",
    "GAME_ACTIONS",
    "get_actions_for_game",
]
