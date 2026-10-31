# commands/game/lib.py
# Game command functions for the casino CLI.
#
# Authorization is delegated to ``casino.access`` -- the
# module-level policy the casino WS handler in
# :mod:`casino.api.handler` uses -- so the local CLI agrees with the
# server's per-op authorization. Game actions are table-bound so the
# actor must be seated at the table to perform them; the policy
# enforces the seat-at check against ``session.table_moniker`` and
# ``message["table_moniker"]``.

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
    "bet": "bet",
    "hit": "hit",
    "stand": "stand",
    "double": "double",
    "split": "split",
}


def bet(args, client=None, **kwargs) -> bool:
    """Place a bet."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["bet"],
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client.cmd_bet()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def hit(args, client=None, **kwargs) -> bool:
    """Hit (blackjack)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["hit"],
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client._loop.run_until_complete(client.send({"type": "hit"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def stand(args, client=None, **kwargs) -> bool:
    """Stand (blackjack)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["stand"],
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client._loop.run_until_complete(client.send({"type": "stand"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def double(args, client=None, **kwargs) -> bool:
    """Double down (blackjack)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["double"],
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client._loop.run_until_complete(client.send({"type": "double"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def split(args, client=None, **kwargs) -> bool:
    """Split hand (blackjack)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["split"],
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client._loop.run_until_complete(client.send({"type": "split"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def game_action(args, action: str, client=None, **kwargs) -> bool:
    """Send a game action (check, call, raise, fold, etc.)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    op = _SUBCMD_TO_OP.get(action, action)
    if not _check_access(
        args,
        op,
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client._loop.run_until_complete(client.send({"type": action}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def play(args, client=None, **kwargs) -> bool:
    """Play a game action - dynamically selected from available_actions."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if getattr(client, "current_table_moniker", None) is None:
        io.echo("Not at a table.", level="error")
        return False

    actions = client.last_available_actions or []
    if not actions:
        io.echo("No actions available. Join a table first.")
        return False

    from casino.client import ActionInputHandler

    handler = ActionInputHandler(
        [{"action": a, "hotkey": "", "label": a} for a in actions]
    )
    action = io.inputstring("Action: ", completer=handler.get_completer())

    resolved = handler.resolve(action)
    if resolved:
        op = _SUBCMD_TO_OP.get(resolved, resolved)
        if not _check_access(
            args,
            op,
            session_moniker=client.moniker,
            table_moniker=getattr(client, "current_table_moniker", None),
        ):
            return False
        client._loop.run_until_complete(client.send({"type": resolved}))
        client._loop.run_until_complete(asyncio.sleep(0.1))
        return True
    io.echo("Invalid action.")
    return False


def menu(args, client=None, **kwargs):
    """Show game operations submenu."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    while True:
        # host.choose: LO when hosted, io.inputchoice standalone. Uppercased for the checks below.
        cmd = (host.choose(
            "{var:promptcolor}[B]et  [H]it  [S]tand  [D]ouble  [P]lay  [L]Split  [Q]uit: {var:inputcolor}", "b,h,s,d,p,l,q", default="q"
        ) or "").upper()

        if cmd == "B":
            bet(args, client=client, **kwargs)
        elif cmd == "H":
            hit(args, client=client, **kwargs)
        elif cmd == "S":
            stand(args, client=client, **kwargs)
        elif cmd == "D":
            double(args, client=client, **kwargs)
        elif cmd == "L":
            split(args, client=client, **kwargs)
        elif cmd == "P":
            play(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True


def _check_access(args, op, *, session_moniker=None, table_moniker=None, **message_fields):
    """Gate a game CLI subcommand through the shared check, with this package's policy."""
    return check_access(
        args,
        op,
        session_moniker=session_moniker,
        table_moniker=table_moniker,
        access=_casino_access,
        **message_fields,
    )
