# commands/bank/lib.py
# Bank command functions for the casino CLI.
#
# Authorization is delegated to ``bbsengine6.bank.access`` -- the same
# module-level policy that ``bed tools bank`` uses -- so the casino
# CLI's bank subcommands and the standalone bed tool agree on what
# each op permits. The CLI uses a per-subcommand ``_check_access``
# helper that mirrors :func:`bed.tools.bank._check_access`: it builds
# a SessionState-like stub from ``args._session_*`` claim-derived
# attributes (set after a successful token-file connect) and lets the
# module-level policy decide.

import argparse
import asyncio
from types import SimpleNamespace
from typing import Any, Dict, Optional

from bbsengine6 import io
from bbsengine6.bank import access as _bank_access

from casino.commands._auth import _require_authenticated_client


# Subcommand -> domain verb understood by ``bbsengine6.bank.access``.
# The bank module owns the verb vocabulary; this dict is the only
# place the CLI needs to maintain the translation. Mirrors
# ``bed.tools.bank._SUBCMD_TO_OP``.
_SUBCMD_TO_OP: Dict[str, str] = {
    "balance": "balance",
    "add": "add",
    "remove": "remove",
    "history": "history",
    "transfer": "transfer",
    "approve": "approve",
    "reject": "reject",
    "pending": "pending",
    "list_all": "list_all",
}


def get_client():
    from casino.client import get_client as _get_client

    return _get_client()


def _make_session(args: argparse.Namespace, moniker: Optional[str] = None) -> SimpleNamespace:
    """Build a SessionState-like stub for ``bbsengine6.bank.access``.

    Precedence for ``.moniker``: explicit argument > claim-derived
    ``args._session_moniker`` (set after a successful token-file
    connect) > explicit ``args.moniker`` flag. Precedence for
    ``.is_sysop``: explicit ``args.sysop`` flag > claim-derived
    ``args._session_is_sysop``.
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
    )


def _resolve_actor_moniker(args: argparse.Namespace, fallback: Optional[str] = None) -> str:
    """Return the actor moniker (who is performing the op).

    Precedence:

    1. ``args._session_moniker`` -- claim-derived from the bearer
       token validated by ``casino.auth._connect_with_token``. When
       set, this wins over everything because the token is the
       cryptographic source of truth for the actor's identity.
    2. ``fallback`` -- the moniker the caller resolved (e.g. via
       interactive prompt). Empty when no fallback was given.
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
    """Gate a bank CLI subcommand through ``bbsengine6.bank.access``.

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
    if _bank_access(args, op, session=synth, message=msg):
        return True
    io.echo(
        f"Operation '{op}' is not permitted for this account.",
        level="error",
    )
    return False


def bank_balance(args, client=None, **kwargs) -> bool:
    """Handle bank balance query."""
    client = _require_authenticated_client(
        client or get_client(), _SUBCMD_TO_OP["balance"]
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["balance"],
        session_moniker=client.moniker,
        moniker=client.moniker,
    ):
        return False
    client.cmd_bank_balance()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_add(args, client=None, **kwargs) -> bool:
    """Handle add funds to bank."""
    client = _require_authenticated_client(
        client or get_client(), _SUBCMD_TO_OP["add"]
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["add"],
        session_moniker=client.moniker,
        moniker=client.moniker,
    ):
        return False
    client.cmd_bank_add()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_remove(args, client=None, **kwargs) -> bool:
    """Handle remove funds from bank."""
    client = _require_authenticated_client(
        client or get_client(), _SUBCMD_TO_OP["remove"]
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["remove"],
        session_moniker=client.moniker,
        moniker=client.moniker,
    ):
        return False
    client.cmd_bank_remove()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_transfer(args, client=None, **kwargs) -> bool:
    """Handle transfer request between tables."""
    client = _require_authenticated_client(
        client or get_client(), _SUBCMD_TO_OP["transfer"]
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["transfer"],
        session_moniker=client.moniker,
        from_=client.moniker,
    ):
        return False
    client.cmd_bank_transfer()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_approve(args, client=None, **kwargs) -> bool:
    """Handle approve transfer."""
    client = _require_authenticated_client(
        client or get_client(), _SUBCMD_TO_OP["approve"]
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["approve"],
        session_moniker=client.moniker,
        responded_by=client.moniker,
    ):
        return False
    client.cmd_bank_approve()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_reject(args, client=None, **kwargs) -> bool:
    """Handle reject transfer."""
    client = _require_authenticated_client(
        client or get_client(), _SUBCMD_TO_OP["reject"]
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["reject"],
        session_moniker=client.moniker,
        responded_by=client.moniker,
    ):
        return False
    client.cmd_bank_reject()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_pending(args, client=None, **kwargs) -> bool:
    """Handle list pending transfers."""
    client = _require_authenticated_client(
        client or get_client(), _SUBCMD_TO_OP["pending"]
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["pending"],
        session_moniker=client.moniker,
        moniker=client.moniker,
    ):
        return False
    client.cmd_bank_pending()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_history(args, client=None, **kwargs) -> bool:
    """Handle bank history query."""
    client = _require_authenticated_client(
        client or get_client(), _SUBCMD_TO_OP["history"]
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["history"],
        session_moniker=client.moniker,
        moniker=client.moniker,
    ):
        return False
    client.cmd_bank_history()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def bank_list_all(args, client=None, **kwargs) -> bool:
    """Handle list all table balances (sysop only)."""
    client = _require_authenticated_client(
        client or get_client(), _SUBCMD_TO_OP["list_all"]
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["list_all"],
        session_moniker=client.moniker,
    ):
        return False
    client.cmd_bank_list_all()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def menu(args, client=None, **kwargs):
    """Show bank operations submenu."""
    client = _require_authenticated_client(
        client or get_client(), "bank menu"
    )
    if client is None:
        return False

    while True:
        cmd = io.inputchoice(
            "{var:promptcolor}[B]alance  [A]dd  [W]ithdraw  [T]ransfer  [P]ending  [H]istory  [L]ist all  [Q]uit: {var:inputcolor}",
            "b,a,w,t,p,h,l,q",
            default="q",
        )

        if cmd == "B":
            bank_balance(args, client=client, **kwargs)
        elif cmd == "A":
            bank_add(args, client=client, **kwargs)
        elif cmd == "W":
            bank_remove(args, client=client, **kwargs)
        elif cmd == "T":
            bank_transfer(args, client=client, **kwargs)
        elif cmd == "P":
            bank_pending(args, client=client, **kwargs)
        elif cmd == "H":
            bank_history(args, client=client, **kwargs)
        elif cmd == "L":
            bank_list_all(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True
