"""
casino/games/menu.py
Auto-derive ``MenuOption`` instances from ``GAME_ACTIONS``.

Each game module that wants its seat-gated menu options to track
``GAME_ACTIONS`` calls ``action_menu_option(action, game_type)`` from
inside its ``menu(args, **kw)`` api (the function it registers via
``register_module(apis={"menu": menu})``). The helper:

  1. Looks up the (letter, label, module_path) tuple for ``action``
     in ``_ACTION_MENU_SPEC``.
  2. Sets ``requires_seated=True`` because every entry in the spec
     represents a table-bound action.
  3. Computes ``allowed_game_types`` by walking ``GAME_ACTIONS`` and
     collecting the game types that support ``action`` -- so adding
     a new game that supports ``action`` automatically widens the
     action's visibility without touching each game module's
     ``menu()``.

The helper is intentionally a function rather than a class so the
caller stays declarative: one ``MenuOption`` per ``GameAction`` in
the registrar's spread.

The spec covers the v1 door-mode surface only (BET, HIT, STAND,
DOUBLE, SPLIT, SPIN, ROLL, LOCK). POKER's CHECK/CALL/RAISE/FOLD/
ALLIN stay out of the menu spec until commands/wiring for them
lands; TICTACTOE's MOVE/JOINT/RESIGN are wired through the
``casino.commands.tictactoe`` shim (not via this helper).
"""

from __future__ import annotations

from bbsengine6.menu_next import MenuOption

from .base import GAME_ACTIONS, GameAction, GameType


_ACTION_MENU_SPEC: dict[GameAction, tuple[str, str, str]] = {
    GameAction.BET:    ("a", "Bet",    "game.bet"),
    GameAction.HIT:    ("h", "Hit",    "game.hit"),
    GameAction.STAND:  ("t", "Stand",  "game.stand"),
    GameAction.DOUBLE: ("d", "Double", "game.double"),
    GameAction.SPLIT:  ("l", "Split",  "game.split"),
    GameAction.SPIN:   ("s", "Spin",   "game.spin"),
    GameAction.ROLL:   ("r", "Roll",   "game.roll"),
    GameAction.LOCK:   ("k", "Lock",   "game.lock"),
}


def action_menu_option(action: GameAction, game_type: GameType) -> MenuOption:
    """Build the ``MenuOption`` for ``action`` on ``game_type``.

    ``allowed_game_types`` is computed from ``GAME_ACTIONS``: every
    game type whose action list contains ``action`` is included. The
    set is frozen so the resulting ``MenuOption`` stays hashable.

    Raises:
        KeyError: if ``action`` is not in ``_ACTION_MENU_SPEC``.
            Callers should only pass v1-surface actions; missing
            keys are a programmer error, not a runtime condition.
    """
    letter, label, module_path = _ACTION_MENU_SPEC[action]
    allowed = frozenset(
        gt.value
        for gt, actions in GAME_ACTIONS.items()
        if action in actions
    )
    return MenuOption(
        letter=letter,
        label=label,
        module_path=module_path,
        requires_seated=True,
        allowed_game_types=allowed,
    )
