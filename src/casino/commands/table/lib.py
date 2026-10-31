# commands/table/lib.py
# Table command functions for the casino CLI.
#
# Authorization is delegated to ``casino.access`` -- the
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
from casino import host
from casino.access import access as _casino_access

# Shared helpers live in commands/_common.py. The underscore names are kept so
# existing callers and tests keep working.
from casino.commands._common import get_client as get_client  # noqa: E402
from casino.commands._common import make_session as _make_session  # noqa: E402
from casino.commands._common import resolve_actor_moniker as _resolve_actor_moniker  # noqa: E402
from casino.commands._common import check_access  # noqa: E402


# Subcommand -> domain verb understood by ``casino.access``.
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
        # host.choose: LO when hosted, io.inputchoice standalone. Uppercased for the checks below.
        cmd = (host.choose(
            "{var:promptcolor}[T]ables  [C]reate  [J]oin  [L]eave  [U]pdate  [V]iew  [Q]uit: {var:inputcolor}",
            "t,c,j,l,u,v,q",
            default="q",
        ) or "").upper()

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


def _check_access(args, op, *, session_moniker=None, table_moniker=None, **message_fields):
    """Gate a table CLI subcommand through the shared check, with this package's policy."""
    return check_access(
        args,
        op,
        session_moniker=session_moniker,
        table_moniker=table_moniker,
        access=_casino_access,
        **message_fields,
    )
