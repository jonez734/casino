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
from casino.access import access as _casino_access


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


def get_client():
    from casino.client import get_client as _get_client

    return _get_client()


def _make_session(args: argparse.Namespace, moniker: Optional[str] = None) -> SimpleNamespace:
    """Build a SessionState-like stub for ``casino.access``.

    Precedence for ``.moniker``: explicit argument > claim-derived
    ``args._session_moniker`` > explicit ``args.moniker`` flag.
    Precedence for ``.is_sysop``: explicit ``args.sysop`` flag >
    claim-derived ``args._session_is_sysop``. ``.table_moniker``
    mirrors ``args._session_table_moniker`` (the actor's currently-
    bound table) so seat-at checks agree with the server.
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
    """Return the actor moniker (who is performing the op)."""
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
    table_moniker: Optional[str] = None,
    **message_fields: Any,
) -> bool:
    """Gate a game CLI subcommand through ``casino.access``.

    Returns True if access is allowed, False otherwise. On False,
    prints a one-line error so the caller can short-circuit.
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
    if table_moniker:
        msg["table_moniker"] = table_moniker
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
        cmd = io.inputchoice(
            "{var:promptcolor}[B]et  [H]it  [S]tand  [D]ouble  [P]lay  [L]Split  [Q]uit: {var:inputcolor}", "b,h,s,d,p,l,q", default="q"
        )

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
