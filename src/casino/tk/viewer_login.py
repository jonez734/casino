"""The round viewer's sign-in: reuse a stored token the daemon still accepts, otherwise ask bed to sign the player in.

The prompt, the login and the token store are bed's :func:`bed.tools.authenticate.authenticate`, the same call every
front end makes. The viewer keeps only the choice to reuse its player's stored token, so it never prompts when a usable
token is already on disk. The token file for a player and terminal is named by bed's ``token_name``.
"""

from __future__ import annotations

import warnings

from bed.tools import token_name


def _configured_spec() -> str:
    """The sign-in callable named by bed.json ``auth.authenticate`` (the bed default when the key is absent)."""
    import json
    from pathlib import Path

    import bed

    path = Path(bed.__file__).resolve().parent / "data" / "bed.json"
    auth = json.loads(path.read_text(encoding="utf-8")).get("auth", {})
    return auth.get("authenticate") or "bed.tools.authenticate:authenticate"


def resolve_authenticate(spec: str):
    """Resolve ``spec`` (``module:attr``) against bbsengine6's sign-in contract. Fails with the key named.

    Raises ValueError for a spec that does not import, and TypeError for a callable that breaks the contract.
    """
    from bbsengine6 import module as be6_module

    try:
        return be6_module.resolve_callable(spec, be6_module._stub_authenticate)
    except (ValueError, TypeError) as exc:
        raise type(exc)(f"auth.authenticate in bed.json: {exc}") from exc


def _authenticate(directory: str, title: str) -> tuple[str, str]:
    """Bed's shared sign-in, for this viewer's window. Returns ``(moniker, token)``; the token is "" on a refusal.

    The callable is resolved from bed.json ``auth.authenticate`` each time it is needed; a bad value raises at startup
    (see ``resolve_authenticate``), before any prompt.
    """
    authenticate = resolve_authenticate(_configured_spec())
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
