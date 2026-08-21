"""casino/games/__init__.py

Backwards-compatible re-export of ``bbsengine6.games``.

The catalog moved to ``bbsengine6.games.base`` and the
menu-derivation helper lives in ``bbsengine6.games.menu``. This
module re-exports both so legacy ``from casino.games import ...``
imports keep working and the helper is reachable through the
``casino.games`` namespace as well.
"""

from bbsengine6.games import (
    GAME_ACTIONS,
    BaseGame,
    GameAction,
    GameType,
    action_menu_option,
    get_actions_for_game,
)

__all__ = [
    "BaseGame",
    "GameType",
    "GameAction",
    "GAME_ACTIONS",
    "get_actions_for_game",
    "action_menu_option",
]
