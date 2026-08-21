"""
casino/games/__init__.py
Game-type catalog and menu-derivation helpers for the casino.

Re-exports the catalog (``GameType``, ``GameAction``, ``GAME_ACTIONS``,
``get_actions_for_game``, ``BaseGame``) so callers can import them
from a single namespace, and exposes the menu-derivation helper
``action_menu_option`` for game modules that want their menu options
auto-derived from ``GAME_ACTIONS``.
"""

from .base import GAME_ACTIONS, BaseGame, GameAction, GameType, get_actions_for_game
from .menu import action_menu_option

__all__ = [
    "BaseGame",
    "GameType",
    "GameAction",
    "GAME_ACTIONS",
    "get_actions_for_game",
    "action_menu_option",
]
