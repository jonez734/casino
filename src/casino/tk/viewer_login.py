"""The round viewer's own login: prompt for moniker and password when no usable token file exists for the player.

Each player has one token file per terminal (see ``token_name``). The viewer reads it, and when it is missing or
rejected it prompts, logs in through bed (the same calls ``bed auth login`` makes) and writes the token it was given.
It never writes a token it did not get from a login, and a failed login writes nothing.
"""

from __future__ import annotations

import argparse
import os

from casino.tk import token_name


def _prompt(moniker: str) -> tuple[str, str]:
    """The moniker and password, prompted with bed's own prompts so the wording matches ``bed auth login``."""
    from bed.tools.auth import _collect_credentials

    return _collect_credentials(argparse.Namespace(moniker=moniker or None, password=None))


def _login(moniker: str, password: str) -> str:
    """Log in through bed on a one-shot connection and return the bearer token, or "" on failure."""
    import asyncio

    from bed.client import get_bed_connection
    from bed.client.authservice import BedAuthServiceClient

    async def run() -> dict:
        return await svc.login(moniker, password)

    svc = BedAuthServiceClient(get_bed_connection(argparse.Namespace(bed_url=None)))
    reply = asyncio.run(run())
    if not reply.get("ok"):
        return ""
    return str(reply.get("token") or "")


def _write(path: str, token: str) -> None:
    """Write ``token`` atomically with mode 0600, in a directory only its owner can read."""
    from bed.tools.auth import _write_token_file

    _write_token_file(path, token)


def _read(path: str) -> str:
    from casino.auth import _read_token_file

    return _read_token_file(path)


def ensure_token(directory: str, moniker: str, *, is_usable, fd: int = 0) -> tuple[str, str]:
    """Return ``(moniker, token)`` for a usable login, logging in and writing the file when there is none.

    ``is_usable(token)`` asks the daemon whether a stored token is still accepted. ``moniker`` may be empty, in which
    case it is prompted for. On failure the token is "" and nothing is written.
    """
    if moniker:
        path = token_name.token_file_path(directory, moniker, fd=fd)
        stored = _read(path)
        if stored and is_usable(stored):
            return moniker.strip().lower(), stored
    name, password = _prompt(moniker)
    path = token_name.token_file_path(directory, name, fd=fd)
    token = _login(name, password)
    if not token:
        return name.strip().lower(), ""
    _write(path, token)
    return name.strip().lower(), token
