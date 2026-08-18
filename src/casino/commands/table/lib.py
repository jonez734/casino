# commands/table/lib.py
# Table command functions for the casino CLI.
#
# Authorization is delegated to ``bbsengine6.casino.access`` -- the
# module-level policy the casino WS handler in
# :mod:`casino.api.handler` uses -- so the local CLI agrees with the
# server's per-op authorization. The CLI uses a per-subcommand
# ``_check_access`` helper that mirrors :func:`bed.tools.bank._check_access`:
# it builds a SessionState-like stub from ``args._session_*`` claim-
# derived attributes (set after a successful token-file connect) and
# lets the module-level policy decide.

import argparse
import asyncio
from types import SimpleNamespace
from typing import Any, Dict, Optional

from bbsengine6 import io
from casino.access import access as _casino_access


# Subcommand -> domain verb understood by ``bbsengine6.casino.access``.
# The casino module owns the verb vocabulary; this dict is the only
# place the CLI needs to maintain the translation.
_SUBCMD_TO_OP: Dict[str, str] = {
    "list": "list_tables",
    "create": "create_table",
    "update": "update_table",
    "join": "join_table",
    "leave": "leave_table",
    "view": "view_table",
}


def get_client():
    from casino.client import get_client as _get_client

    return _get_client()


def _make_session(args: argparse.Namespace, moniker: Optional[str] = None) -> SimpleNamespace:
    """Build a SessionState-like stub for ``bbsengine6.casino.access``.

    Precedence for ``.moniker``: explicit argument > claim-derived
    ``args._session_moniker`` (set after a successful token-file
    connect) > explicit ``args.moniker`` flag. Precedence for
    ``.is_sysop``: explicit ``args.sysop`` flag > claim-derived
    ``args._session_is_sysop``. ``.table_moniker`` mirrors
    ``args._session_table_moniker`` (the actor's currently-bound
    table, if any) so seat-at checks agree with the server.
    """
    return SimpleNamespace(
        moniker=(
            (moniker or "").strip()
            or getattr(args, "_session_moniker", None)
            or getattr(args, "moniker", None)
            or ""
        ),
        is_sysop=bool(
            getattr(args, "sysop", False)
            or getattr(args, "_session_is_sysop", False)
        ),
        table_moniker=(
            getattr(args, "_session_table_moniker", None) or None
        ),
    )


def _resolve_actor_moniker(args: argparse.Namespace, fallback: Optional[str] = None) -> str:
    """Return the actor moniker (who is performing the op).

    Precedence:

    1. ``args._session_moniker`` -- claim-derived from the bearer
       token validated by ``casino.auth._connect_with_token``. When
       set, this wins over everything because the token is the
       cryptographic source of truth for the actor's identity.
    2. ``fallback`` -- the moniker the caller resolved.
    3. ``args.moniker`` -- the explicit ``--moniker`` flag.
    """
    return (
        getattr(args, "_session_moniker", "")
        or (fallback or "")
        or getattr(args, "moniker", "")
        or ""
    ).strip()


def _check_access(
    args: argparse.Namespace,
    op: str,
    *,
    session_moniker: Optional[str] = None,
    **message_fields: Any,
) -> bool:
    """Gate a table CLI subcommand through ``bbsengine6.casino.access``.

    Returns True if access is allowed, False otherwise. On False,
    prints a one-line error so the caller can short-circuit.

    The session-bound gate is checked first: if the resolved actor
    moniker is empty, the subcommand is denied unconditionally. This
    matches the WS handler's session gate so the local CLI agrees
    with the server.
    """
    actor = _resolve_actor_moniker(args, fallback=session_moniker)
    synth = _make_session(args, moniker=actor)
    if not (synth.moniker or "").strip():
        io.echo(
            f"Operation '{op}' requires an authenticated session.",
            level="error",
        )
        return False
    msg = {}
    for k, v in message_fields.items():
        if v is None:
            continue
        msg[k] = v
    if _casino_access(args, op, session=synth, message=msg):
        return True
    io.echo(
        f"Operation '{op}' is not permitted for this account.",
        level="error",
    )
    return False


def list_tables(args, client=None, **kwargs) -> bool:
    """List available tables."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["list"],
        session_moniker=client.moniker,
    ):
        return False
    client.cmd_list_tables()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def create_table(args, client=None, **kwargs) -> bool:
    """Create a new table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["create"],
        session_moniker=client.moniker,
    ):
        return False
    client.cmd_create_table()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def update_table(args, client=None, **kwargs) -> bool:
    """Update table settings."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["update"],
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client.cmd_update_table()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def join_table(args, client=None, **kwargs) -> bool:
    """Join a table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["join"],
        session_moniker=client.moniker,
    ):
        return False
    client.cmd_join_table()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def leave_table(args, client=None, **kwargs) -> bool:
    """Leave current table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["leave"],
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client.cmd_leave_table()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def view_table(args, client=None, **kwargs) -> bool:
    """View current table status."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if getattr(client, "current_table_moniker", None) is None:
        io.echo("Not at a table.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["view"],
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client._loop.run_until_complete(
        client.send(
            {
                "type": "view_table",
                "moniker": getattr(client, "current_table_moniker", None),
            }
        )
    )
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def menu(args, client=None, **kwargs):
    """Show table operations submenu."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    while True:
        cmd = io.inputchoice(
            "{var:promptcolor}[T]ables  [C]reate  [J]oin  [L]eave  [U]pdate  [V]iew  [Q]uit: {var:inputcolor}",
            "t,c,j,l,u,v,q",
            default="q",
        )

        if cmd == "T":
            list_tables(args, client=client, **kwargs)
        elif cmd == "C":
            create_table(args, client=client, **kwargs)
        elif cmd == "J":
            join_table(args, client=client, **kwargs)
        elif cmd == "L":
            leave_table(args, client=client, **kwargs)
        elif cmd == "U":
            update_table(args, client=client, **kwargs)
        elif cmd == "V":
            view_table(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True
