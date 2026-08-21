# casino/menu_lib.py
# Shared menu visibility helpers.
#
# Pure data structure + filter logic. No I/O, no DB, no logging.
# Import policy:
#   - ``bbsengine6.io`` is permitted (psycopg-free at module load).
#   - ``bbsengine6.util`` is forbidden because it transitively imports
#     ``bbsengine6.database`` which loads ``psycopg`` at module load.
#     Don't add ``from bbsengine6 import util`` to this file; route any
#     utility calls through the consumer's already-imported bbsengine6
#     symbols.
#
# Consumers (door-mode ``casino.main``, WS-client ``casino.client.menu``,
# ``casino.commands.slots.lib``) all pass a duck-typed ``state`` object
# that exposes ``current_table_moniker`` and
# ``current_table_game_type``; the WS client and door-mode also expose
# ``connected``. Missing attributes are treated as ``None`` / ``False``
# so a partially-initialised state object is safe.

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class MenuOption:
    """A single menu option.

    Attributes:
        letter: single lowercase letter; consumer displays ``letter.upper()``.
        label: short label fragment for the inline prompt (e.g. ``"et"``),
            or full label for the help screen (e.g. ``"Blackjack"``).
        module_path: dispatch target (e.g. ``"blackjack.play"``).
        requires_seated: True when the player must be at a table
            (``state.current_table_moniker`` set) for the option to be
            shown.
        allowed_game_types: optional frozenset of game types for which
            the option is meaningful. When set and ``requires_seated``
            is True, the option is hidden unless
            ``state.current_table_game_type`` is in the set (including
            the post-join window when the game type is still ``None``).
        hide_if_seated_type: optional frozenset of game types; when the
            player is seated at a table whose ``game_type`` is in this
            set, the option is hidden. Used to hide game launchers for
            the game the player is already playing.
        requires_connected: True when the player must be connected
            (``state.connected`` truthy) for the option to be shown.
            Typical use: hide ``Disconnect`` when no connection exists.
    """

    letter: str
    label: str
    module_path: Optional[str] = None
    requires_seated: bool = False
    allowed_game_types: Optional[frozenset] = None
    hide_if_seated_type: Optional[frozenset] = None
    requires_connected: bool = False


def visible_options(
    spec: Iterable[MenuOption],
    state: Any,
) -> list[MenuOption]:
    """Return the subset of ``spec`` the player may currently pick.

    The ``state`` object is duck-typed. The helper reads:

    - ``state.current_table_moniker`` (truthy means seated)
    - ``state.current_table_game_type`` (string or ``None``)
    - ``state.connected`` (truthy means a connection is open)

    Missing attributes are treated as ``None`` / ``False`` so partial
    state objects (e.g. a freshly-constructed ``CasinoPlayer`` before
    ``_load()`` finishes) do not raise.

    Gates run in this order:

    1. ``requires_seated`` — drop if not seated.
    2. ``allowed_game_types`` (combined with ``requires_seated``) —
       drop if the seated table's game type is unknown or outside the
       set. Covers the brief window between ``join_table`` and the
       first ``game_state`` reply.
    3. ``hide_if_seated_type`` — drop if the player is seated at a
       table whose game type is in the set (e.g. hide the Blackjack
       launcher when already at a blackjack table).
    4. ``requires_connected`` — drop if no connection.

    The order matters only when multiple gates would fire on the same
    option; any firing gate drops the option.
    """
    seated = bool(state and getattr(state, "current_table_moniker", None))
    gt_raw = getattr(state, "current_table_game_type", None)
    gt = (gt_raw.strip() if isinstance(gt_raw, str) else None) or None
    connected = bool(getattr(state, "connected", False))
    out: list[MenuOption] = []
    for opt in spec:
        if opt.requires_seated and not seated:
            continue
        if opt.requires_seated and opt.allowed_game_types and gt not in opt.allowed_game_types:
            continue
        if opt.hide_if_seated_type and seated and gt in opt.hide_if_seated_type:
            continue
        if opt.requires_connected and not connected:
            continue
        out.append(opt)
    return out
