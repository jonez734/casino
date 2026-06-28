# casino/client/registry.py
# Client registry: tracks active CasinoClient instances by moniker.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .casino_client import CasinoClient


_clients: dict[str, CasinoClient] = {}
_current_moniker: str | None = None


def get_client(moniker: str | None = None) -> CasinoClient | None:
    """Get a client by moniker, or the current moniker if None."""
    if moniker is None:
        moniker = _current_moniker
    return _clients.get(moniker)


def get_current_moniker() -> str | None:
    """Get the current active moniker."""
    return _current_moniker


def set_current_moniker(moniker: str | None) -> None:
    """Set the current active moniker."""
    global _current_moniker
    _current_moniker = moniker
