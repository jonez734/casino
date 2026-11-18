"""The round viewer's sign-in: reuse a stored token the daemon still accepts, otherwise ask bed to sign the player in.

The prompt, the login and the token store are bed's :func:`bed.tools.authenticate.authenticate`, the same call every
front end makes. The viewer keeps only the choice to reuse its player's stored token, so it never prompts when a usable
token is already on disk. The token file for a player and terminal is named by bed's ``token_name``.
"""

from __future__ import annotations

import warnings

from bed.tools import token_name


def _authenticate(directory: str, title: str) -> tuple[str, str]:
    """Bed's shared sign-in, for this viewer's window. Returns ``(moniker, token)``; the token is "" on a refusal."""
    from bed.tools.authenticate import authenticate

    return authenticate(directory=directory, title=title, store_token=True)


def _read(path: str) -> str:
    from casino.auth import _read_token_file

    return _read_token_file(path)


def ensure_token(directory: str, moniker: str, *, is_usable, fd: int = 0) -> tuple[str, str]:
    """Return ``(moniker, token)``: a stored token the daemon accepts, else a fresh sign-in through bed's authenticate.

    ``is_usable(token)`` asks the daemon whether a stored token is still accepted. On a refusal the token is "".
    """
    if moniker:
        stored = _read(token_name.token_file_path(directory, moniker, fd=fd))
        if stored and is_usable(stored):
            return moniker.strip().lower(), stored
    return _authenticate(directory, "round-view login")
