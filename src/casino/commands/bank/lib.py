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
from casino import host
from bbsengine6.bank import access as _bank_access

from casino.commands._auth import _require_authenticated_client

# Shared helpers live in commands/_common.py. The underscore names are kept so
# existing callers and tests keep working.
from casino.commands._common import get_client as get_client  # noqa: E402
from casino.commands._common import make_session as _make_session  # noqa: E402
from casino.commands._common import resolve_actor_moniker as _resolve_actor_moniker  # noqa: E402
from casino.commands._common import check_access  # noqa: E402


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
        # host.choose: LO when hosted, io.inputchoice standalone. Uppercased for the checks below.
        cmd = (host.choose(
            "{var:promptcolor}[B]alance  [A]dd  [W]ithdraw  [T]ransfer  [P]ending  [H]istory  [L]ist all  [Q]uit: {var:inputcolor}",
            "b,a,w,t,p,h,l,q",
            default="q",
        ) or "").upper()

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


def _check_access(args, op, *, session_moniker=None, table_moniker=None, **message_fields):
    """Gate a bank CLI subcommand through the shared check, with this package's policy."""
    return check_access(
        args,
        op,
        session_moniker=session_moniker,
        table_moniker=table_moniker,
        access=_bank_access,
        **message_fields,
    )
