"""Bottom bar for the bed-connected casino client.

Left: the current table moniker (blank when not seated).
Right: the signed-in moniker and the player's bank balance.

The client keeps its own state (``moniker``, ``balance``, ``current_table_moniker``).
This module reads that state through a provider, so the bar always shows what the
client knows. It reuses bbsengine6's bottombar registry; the client gets a registry of
its own, so it cannot clash with door mode's ``casino`` registry.
"""

from __future__ import annotations

import sys
from typing import Any, Callable, Optional

from bbsengine6 import bottombar, io

REGISTRY_NAME = "casino.client"

_registry = bottombar.registry_for(REGISTRY_NAME)
_provider: Optional[Callable[[], Any]] = None


def _state() -> Any:
    return _provider() if _provider is not None else None


def _moniker_fragment(**kwargs) -> str:
    client = _state()
    moniker = getattr(client, "moniker", "") if client is not None else ""
    return f"{moniker}" if moniker else ""


def _balance_fragment(**kwargs) -> str:
    client = _state()
    if client is None or not getattr(client, "authenticated", False):
        return ""
    return f"bank {getattr(client, 'balance', 0)}"


def _table_left(**kwargs) -> str:
    """Left side: the seated table, its game type, and the play clock when one is running."""
    from casino.client.clock_display import countdown_text
    client = _state()
    table = getattr(client, "current_table_moniker", None) if client is not None else None
    if not table:
        return ""
    game_type = getattr(client, "current_table_game_type", None)
    label = f"table: {table}" + (f" ({game_type})" if game_type else "")
    clock = countdown_text(getattr(client, "current_table_deadline", None))
    return f"{label}  {clock}" if clock else label


_FRAGMENTS = (_moniker_fragment, _balance_fragment)

# The renderer leaves a wide right side untrimmed, so a long moniker could push the line past the
# terminal and wrap it. The right side is capped here so the balance always fits; the moniker
# gives way first.
_MIN_LEFT_COLUMNS = 12


def _right_side(width: int) -> str:
    """The right side of the bar, capped so the line fits ``width`` columns with some left room."""
    moniker = _moniker_fragment()
    balance = _balance_fragment()
    parts = [p for p in (moniker, balance) if p]
    text = " | ".join(parts)
    budget = max(0, width - 2 - _MIN_LEFT_COLUMNS)
    if len(text) <= budget:
        return text
    if balance and len(balance) <= budget:
        # Keep the balance whole; drop the moniker, cut to fit what is left.
        return balance
    return balance[-budget:] if budget else ""


def attach(provider: Callable[[], Any]) -> None:
    """Bind the bar to a client. ``provider`` returns the live client object."""
    global _provider
    _provider = provider
    for fn in _FRAGMENTS:
        if fn not in _registry:
            _registry.register(fn)


def detach() -> None:
    """Remove the client's fragments and clear the bottom row."""
    global _provider
    for fn in _FRAGMENTS:
        _registry.unregister(fn)
    _provider = None
    if not sys.stdout.isatty():
        return  # nothing drawn on a non-terminal, so nothing to clear
    io.echo("{savecursor}{curpos:%s,0}{el}{reset}{restorecursor}" % _bottom_row())


def _bottom_row() -> int:
    from bbsengine6.io import terminal

    return terminal.height()


def redraw(args: Any = None) -> None:
    """Draw the bar: table on the left, moniker and balance on the right.

    ``args`` is only used by bbsengine6 to stash context; the client's state comes from
    the provider, so ``args`` may be None.
    """
    if _provider is None:
        return
    bottombar.set_context_for(REGISTRY_NAME, args=args)
    width = bottombar.terminal.width()
    bottombar._render_bottombar(_registry, _table_left, lambda **_: _right_side(width))
