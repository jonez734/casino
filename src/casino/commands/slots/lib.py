# commands/slots/lib.py
# Slots command functions. WS-backed: every op sends through the
# connected ``CasinoClient`` so ``CasinoClient.send`` auto-injects the
# bearer token on every wire call. Mirrors ``commands/bank/lib.py``
# (which uses ``bbsengine6.bank.access``) and ``commands/table/lib.py``
# (which uses ``bbsengine6.casino.access``); the gate here uses
# ``bbsengine6.casino.access`` so the local CLI's authorization agrees
# with the WS handler in :mod:`casino.api.handler`.
#
# The legacy door-mode play loop lives in ``casino/slots/play.py`` and
# is reachable via ``casino.slots --door`` for offline smoke testing.
# The BBS menu path here is WS-backed only -- there is no offline /
# unauthenticated fallback, because slot spins touch the bank account
# and must be authorized by a valid session.

import argparse
import asyncio
from types import SimpleNamespace
from typing import Any, Dict, Optional

from bbsengine6 import io, util
from casino.access import access as _casino_access


# Subcommand -> domain verb understood by ``bbsengine6.casino.access``.
# The casino module owns the verb vocabulary; this dict is the only
# place the CLI needs to maintain the translation.
_SUBCMD_TO_OP: Dict[str, str] = {
    "spin": "slot_spin",
    "paytable": "slot_paytable",
    "history": "slot_history",
}


def get_client():
    from casino.client import get_client as _get_client

    return _get_client()


def _make_session(
    args: argparse.Namespace, moniker: Optional[str] = None
) -> SimpleNamespace:
    """Build a SessionState-like stub for ``bbsengine6.casino.access``.

    Precedence for ``.moniker``: explicit argument > claim-derived
    ``args._session_moniker`` (set after a successful token-file
    connect) > explicit ``args.moniker`` flag. Precedence for
    ``.is_sysop``: explicit ``args.sysop`` flag > claim-derived
    ``args._session_is_sysop``. ``.table_moniker`` mirrors the
    actor's currently-bound table so seat-at checks agree with the
    server.
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


def _resolve_actor_moniker(
    args: argparse.Namespace, fallback: Optional[str] = None
) -> str:
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
    table_moniker: Optional[str] = None,
    **message_fields: Any,
) -> bool:
    """Gate a slots CLI subcommand through ``bbsengine6.casino.access``.

    Returns True if access is allowed, False otherwise. On False,
    prints a one-line error so the caller can short-circuit.

    The session-bound gate is checked first: if the resolved actor
    moniker is empty, the subcommand is denied unconditionally. This
    matches the WS handler's session gate so the local CLI agrees
    with the server. ``slot_history`` is a self-or-sysop op (the
    caller passes ``moniker=`` for the target), so ``_check_access``
    forwards it through ``message_fields`` for the policy to read.
    """
    actor = _resolve_actor_moniker(args, fallback=session_moniker)
    synth = _make_session(args, moniker=actor)
    if not (synth.moniker or "").strip():
        io.echo(
            f"Operation '{op}' requires an authenticated session.",
            level="error",
        )
        return False
    msg: Dict[str, Any] = {}
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


def _require_authenticated_client(
    client, op: str
) -> Optional[Any]:
    """Defense-in-depth: refuse if no client or the client hasn't
    actually finished authenticating.

    ``get_client()`` only returns a registered client after a
    successful connect, so ``client is None`` already covers the
    never-connected case. The extra checks here cover edge cases
    where the registry holds a half-built client (auth aborted,
    token rejected, disconnect in flight): if
    ``client.authenticated`` is False or ``client.moniker`` is empty,
    the wire op would not carry a valid claim-derived identity and
    the server-side ``bbsengine6.casino.access`` gate would deny it
    anyway. We short-circuit here so the CLI matches.
    """
    if client is None:
        io.echo(
            f"Operation '{op}' requires an authenticated session. "
            f"Use Connect first.",
            level="error",
        )
        return None
    if not getattr(client, "authenticated", False):
        io.echo(
            f"Operation '{op}' requires an authenticated session. "
            f"Authentication did not complete.",
            level="error",
        )
        return None
    if not (getattr(client, "moniker", "") or "").strip():
        io.echo(
            f"Operation '{op}' requires an authenticated session. "
            f"Client has no moniker.",
            level="error",
        )
        return None
    return client


def play(args: argparse.Namespace, client=None, **kwargs) -> bool:
    """Start a slot spin via the WS client.

    Kept under the name ``play`` for backwards compatibility with
    callers that wire ``SUBCOMMANDS["play"]`` or the ``play`` sub-
    command path. Delegates to :func:`slot_spin` so a single sub-
    command drives the same flow.
    """
    return slot_spin(args, client=client, **kwargs)


def slot_spin(args: argparse.Namespace, client=None, **kwargs) -> bool:
    """Send a slot_spin wire op through the connected client.

    The client gate is checked first so a missing / disconnected /
    unauthorized session fails before any WS send. The wire call
    auto-injects the bearer token via ``CasinoClient.send`` so the
    server's ``casino.api._auth.check_access`` re-verifies it on
    every op (defense in depth, mirroring ``bed.api.bank.BankService``).
    """
    client = _require_authenticated_client(
        client or get_client(), "slot_spin"
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["spin"],
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client.cmd_slot_spin()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def slot_paytable(args: argparse.Namespace, client=None, **kwargs) -> bool:
    """Send a slot_paytable wire op through the connected client."""
    client = _require_authenticated_client(
        client or get_client(), "slot_paytable"
    )
    if client is None:
        return False
    if not _check_access(
        args,
        _SUBCMD_TO_OP["paytable"],
        session_moniker=client.moniker,
        table_moniker=getattr(client, "current_table_moniker", None),
    ):
        return False
    client.cmd_slot_paytable()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def slot_history(args: argparse.Namespace, client=None, **kwargs) -> bool:
    """Send a slot_history wire op through the connected client.

    ``slot_history`` is a self-or-sysop op; the access policy reads
    ``message["moniker"]`` as the target. We pass the actor's own
    moniker so the server returns the actor's spins.
    """
    client = _require_authenticated_client(
        client or get_client(), "slot_history"
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
    client.cmd_slot_history()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def _render_help(**kwargs) -> None:
    """F1/HELP callback for the slots submenu.

    Per the spec: util.heading() is called exactly once per display of
    help, then the option list is echoed.
    """
    util.heading("Slots")
    io.echo("{var:optioncolor}[S]{var:labelcolor}pin (place a bet and pull the lever)")
    io.echo("{var:optioncolor}[P]{var:labelcolor}aytable (show the table's paytable)")
    io.echo("{var:optioncolor}[H]{var:labelcolor}istory (list your recent spins)")
    io.echo("{var:optioncolor}[Q]{var:labelcolor}uit to main menu")


def menu(args: argparse.Namespace, client=None, **kwargs):
    """Show the slots submenu and dispatch the chosen subcommand.

    Refuses to open if no authenticated client is registered. The
    gate fires before the heading / help / prompt so a user who
    hasn't connected cannot even see the [S]pin option. Every
    option that does run goes through the WS client, so the bearer
    token is auto-injected on every wire call (see
    ``CasinoClient.send``) and the server-side
    ``bbsengine6.casino.access`` re-verifies it.
    """
    client = _require_authenticated_client(
        client or get_client(), "slots menu"
    )
    if client is None:
        return True

    util.heading("Slots")
    _render_help()
    cmd = io.inputchoice(
        "{var:promptcolor}[S]pin  [P]aytable  [H]istory  [Q]uit: {var:inputcolor}",
        "s,p,h,q",
        default="q",
        help=_render_help,
    )

    if cmd == "S":
        slot_spin(args, client=client, **kwargs)
    elif cmd == "P":
        slot_paytable(args, client=client, **kwargs)
    elif cmd == "H":
        slot_history(args, client=client, **kwargs)

    return True
