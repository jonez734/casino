# commands/_common.py
# Code shared by every command package under ``casino.commands``.
#
# Each package keeps only what is particular to it: its SUBCOMMANDS map, its
# ``access()`` rules, its ``version()`` delegate, and any extra ``buildargs()``
# arguments. Everything else is here, once.

from __future__ import annotations

import argparse
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, Optional

from bbsengine6 import io, register_module
from casino.access import access as _casino_access


def get_client():
    """The connected WebSocket client for the current session, or None."""
    from casino.client import get_client as _get_client

    return _get_client()


def make_session(args: argparse.Namespace, moniker: Optional[str] = None) -> SimpleNamespace:
    """Build a SessionState-like stub for ``casino.access``.

    Precedence for ``.moniker``: explicit argument > claim-derived
    ``args._session_moniker`` (set after a successful token-file connect)
    > explicit ``args.moniker`` flag. Precedence for ``.is_sysop``: explicit
    ``args.sysop`` flag > claim-derived ``args._session_is_sysop``.
    ``.table_moniker`` mirrors ``args._session_table_moniker`` so seat-at
    checks agree with the server.
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
        table_moniker=(getattr(args, "_session_table_moniker", None) or None),
    )


def resolve_actor_moniker(args: argparse.Namespace, fallback: Optional[str] = None) -> str:
    """Return the actor moniker (who is performing the op).

    Precedence:

    1. ``args._session_moniker`` -- claim-derived from the bearer token. It
       wins because the token is the source of truth for identity.
    2. ``fallback`` -- the moniker the caller resolved.
    3. ``args.moniker`` -- the explicit ``--moniker`` flag.
    """
    return (
        getattr(args, "_session_moniker", "")
        or (fallback or "")
        or getattr(args, "moniker", "")
        or ""
    ).strip()


def check_access(
    args: argparse.Namespace,
    op: str,
    *,
    session_moniker: Optional[str] = None,
    table_moniker: Optional[str] = None,
    access: Optional[Callable[..., bool]] = None,
    **message_fields: Any,
) -> bool:
    """Gate a command through the access policy.

    ``access`` is the policy function. A package passes its own module-level
    ``_casino_access`` so the package's policy can be patched in tests. It
    defaults to ``casino.access.access``.

    Returns True when access is allowed. On False it prints a one-line error so
    the caller can stop. A session with no resolved actor is refused before the
    policy runs. ``table_moniker`` is added to the message when given, for
    commands that act on a table.
    """
    policy = access if access is not None else _casino_access
    actor = resolve_actor_moniker(args, fallback=session_moniker)
    synth = make_session(args, moniker=actor)
    if not (synth.moniker or "").strip():
        io.echo(
            f"Operation '{op}' requires an authenticated session.",
            level="error",
        )
        return False
    msg: Dict[str, Any] = {}
    for k, v in message_fields.items():
        if v is not None:
            msg[k] = v
    if table_moniker:
        msg["table_moniker"] = table_moniker
    if policy(args, op, session=synth, message=msg):
        return True
    io.echo(
        f"Operation '{op}' is not permitted for this account.",
        level="error",
    )
    return False


def resolve_subcommand(
    input_str: Optional[str],
    subcommands: Dict[str, Callable],
    report: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """Resolve a typed subcommand to its key in ``subcommands``.

    An exact match wins. Otherwise a unique prefix matches. An ambiguous prefix
    resolves to None and is passed to ``report`` (a package's own error echo).
    """
    if not input_str:
        return None
    if input_str in subcommands:
        return input_str
    lowered = input_str.lower()
    if lowered in subcommands:
        return lowered
    matches = [name for name in subcommands if name.startswith(lowered)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        message = f"Ambiguous: '{input_str}' could be {', '.join(matches)}"
        (report or (lambda m: io.echo(m, level="error")))(message)
    return None


def register(name: str, module_path: str, version: str) -> bool:
    """The shared ``init()`` body: register a command package with bbsengine6."""
    register_module(
        name=name,
        module_path=module_path,
        version=version,
        apis={},
    )
    return True


def show_version(name: str, version: str) -> bool:
    """Print a command package's version. Used for ``--version``. Does not connect."""
    io.echo(f"casino {name} {version}")
    return True


def build_parser(
    prog: str,
    subcommands: Optional[Iterable[str]] = None,
    extra: Optional[Callable[[argparse.ArgumentParser], None]] = None,
) -> argparse.ArgumentParser:
    """Build a package's parser. It always exists, so ``buildargs()`` never returns None.

    Every parser accepts ``--version``. A package with subcommands gets a
    ``subcommand`` positional restricted to those names. ``extra`` adds the
    package's own arguments.
    """
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("--version", action="store_true", dest="version")
    if subcommands is not None:
        parser.add_argument(
            "subcommand",
            nargs="?",
            choices=sorted(subcommands),
            help="subcommand to run",
        )
    if extra is not None:
        extra(parser)
    return parser


def dispatch(
    args: Any,
    subcommands: Dict[str, Callable],
    menu: Callable,
    version_text: str,
    name: str,
    **kw: Any,
) -> bool:
    """The shared ``main()``.

    ``--version`` prints ``version_text`` and returns without running anything.
    A missing subcommand opens the package's submenu. A known subcommand runs
    its function. An unknown one is reported, then the submenu opens.
    """
    if kw.get("version"):
        return show_version(name, version_text)

    subcommand = kw.get("subcommand")
    if subcommand is None:
        menu(args, **kw)
        return True

    resolved = resolve_subcommand(subcommand, subcommands)
    if resolved is not None:
        subcommands[resolved](args, **kw)
    else:
        io.echo(f"Unknown subcommand: {subcommand}", level="error")
        menu(args, **kw)
    return True
