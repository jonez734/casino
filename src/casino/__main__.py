# casino/__main__.py
# Entry point for the merged ``casino`` CLI.
#
# Routing:
#
# - ``casino <command> [...]`` (admin, bank, chat, game, poker, slots,
#   table, yahtzee): runs one command package through the bed WebSocket
#   client. ``--version`` is handled first and does not connect.
#
# - default: bed WebSocket client. Probes the bed daemon on
#   ``--bed-host/--bed-port``; if reachable, instantiates
#   ``CasinoClient`` and runs the terminal UI loop. If unreachable,
#   re-raises :class:`bed.tools._routing.BedNotReachable`.
#
# Casino has no door mode. The menu and the games run only through bed,
# so every path above needs a reachable bed daemon.
#
# Backend selection is delegated to :func:`casino._routing.select_backend`,
# which mirrors the convention used by every tool under ``bed.tools``.

from __future__ import annotations

import argparse
import locale
import sys
import time
from argparse import Namespace

from bbsengine6 import bottombar, database, io, session
from bed.tools._routing import BedNotReachable

from . import _routing, lib
from .client import CasinoClient


def _run_bed(args: Namespace) -> int:
    """Default branch: talk to the bed daemon through CasinoClient.

    Initializes the user's locale before constructing the client so that
    locale-formatted numeric cells (e.g. ``f"{n:n}"`` for thousands
    separators) render with the expected group character. The direct and
    blackjack branches already do this; the WS-client branch was the
    odd one out.
    """
    locale.setlocale(locale.LC_ALL, "")
    time.tzset()

    client = CasinoClient(args)
    client.run()
    # A quit, EOF, or Ctrl-C after a successful login is a normal stop (0). Only a
    # session that never authenticated is a failure (1).
    if getattr(client, "_exit_reason", None) == "auth_failed":
        return 1
    return 0 if getattr(client, "authenticated", False) or getattr(client, "_exit_reason", None) in ("quit", "eof", "intr") else 1


def _run_opencode(args: Namespace) -> int:
    """``casino --install-opencode`` / ``--uninstall-opencode``: opencode's own grants.

    Defaults to zoid6test. A live database needs --allow-live and --confirm <name>.
    """
    from casino import opencode_grants as og

    explicit = any(a == "--databasename" or a.startswith("--databasename=") for a in sys.argv)
    database_name = args.databasename if explicit else og.DEFAULT_DATABASE
    allow_live = bool(getattr(args, "allow_live", False))
    confirmation = getattr(args, "confirm", None)
    try:
        if getattr(args, "install_opencode", False):
            ok = og.install(args, database=database_name, allow_live=allow_live, confirmation=confirmation)
        else:
            ok = og.uninstall(args, database=database_name, allow_live=allow_live, confirmation=confirmation)
    except og.LiveDatabaseRefused as e:
        io.echo(f"{{level.error}}casino opencode grants: {e}", level="error")
        return 1
    return 0 if ok else 1


def _run_cleanup_test_state(args: Namespace) -> int:
    """``casino --cleanup-test-state``: opencode cleans what it can; the rest goes to a jam file."""
    from casino import cleanup_test_state as cts

    explicit = any(a == "--databasename" or a.startswith("--databasename=") for a in sys.argv)
    database_name = args.databasename if explicit else cts.DEFAULT_DATABASE
    try:
        return 0 if cts.run(
            args,
            database=database_name,
            allow_live=bool(getattr(args, "allow_live", False)),
            confirmation=getattr(args, "confirm", None),
        ) else 1
    except cts.LiveDatabaseRefused as e:
        io.echo(f"{{level.error}}casino cleanup-test-state: {e}", level="error")
        return 1


def _run_test_data(args: Namespace) -> int:
    """``casino --install-test-data`` / ``--uninstall-test-data``: the bed test fixtures.

    Defaults to zoid6test. A live database needs --allow-live and --confirm <name>.
    """
    from casino import test_data

    # The parser defaults --databasename to zoid6test, so the scratch database is used unless the
    # operator passed --databasename explicitly (sys.argv records that).
    explicit = any(a == "--databasename" or a.startswith("--databasename=") for a in sys.argv)
    database_name = args.databasename if explicit else test_data.DEFAULT_DATABASE
    try:
        test_data.check_target(
            database_name,
            allow_live=bool(getattr(args, "allow_live", False)),
            confirmation=getattr(args, "confirm", None),
        )
    except test_data.LiveDatabaseRefused as e:
        io.echo(f"{{level.error}}casino test data: {e}", level="error")
        return 1

    if getattr(args, "install_test_data", False):
        ok = test_data.install(args, database=database_name,
                               allow_live=bool(getattr(args, "allow_live", False)),
                               confirmation=getattr(args, "confirm", None))
    else:
        ok = test_data.uninstall(args, database=database_name,
                                 allow_live=bool(getattr(args, "allow_live", False)),
                                 confirmation=getattr(args, "confirm", None))
    return 0 if ok else 1


def _run_install(args: Namespace) -> int:
    """``casino --install`` branch: casino's database setup, once per install.

    Casino requires bed. The bed engine schema must already exist (bed's
    own bootstrap creates it), and the connecting role must be a superuser
    or a member of zoid6. Both are checked here before any DDL runs.
    Target database comes from ``--databasename``.
    """
    from bed.startup import verify_install

    from bbsengine6.backend import checksuperuser
    from casino.startup import main as casino_startup

    if not verify_install(args):
        io.echo(
            "{level.error}casino --install: bed's engine schema is missing; "
            "run 'bed --install' first",
            level="error",
        )
        return 1

    with database.context_pool(args, dbname=args.databasename) as pool, \
            database.connect(args, pool=pool) as conn:
        if checksuperuser.main(args, conn=conn) is not True:
            io.echo(
                "{level.error}casino --install: connecting role is not a superuser "
                "or zoid6 member",
                level="error",
            )
            return 1

    if casino_startup(args) is not True:
        io.echo("{level.error}casino --install failed", level="error")
        return 1

    io.echo("{level.ok}casino --install complete", level="ok")
    return 0


# Command packages reachable as ``casino <name> [...]`` from the command line.
_COMMAND_PACKAGES = (
    "admin", "bank", "chat", "game", "poker", "slots", "table", "yahtzee",
)


def _print_command_version(name: str) -> int:
    """Print ``casino <name> <version>`` and return 0. Does not connect."""
    import importlib

    pkg = importlib.import_module(f"casino.commands.{name}")
    io.echo(f"casino {name} {pkg.__version__}")
    return 0


def _run_command(name: str, args: Namespace, cmd_argv: list) -> int:
    """``casino <name> [...]``: run one command package against a connected client.

    Connects and authenticates through the bed WebSocket, runs the package's
    ``main()`` with the connected client, then disconnects. ``args`` is the
    top-level parse (bed host and port, token file).
    """
    from bbsengine6 import module

    client = CasinoClient(args)

    def run() -> None:
        subcommand = cmd_argv[0] if cmd_argv else None
        kw = {"subcommand": subcommand, "client": client}
        module.run(args, "main", package=f"casino.commands.{name}", **kw)

    client.run_once(run)
    return 0 if getattr(client, "authenticated", False) else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # ``casino <command> --version`` prints that command's version. Routed before the
    # top-level parse, whose own --version action would otherwise print the casino
    # version and exit first.
    if len(argv) >= 2 and argv[0] in _COMMAND_PACKAGES and argv[1] == "--version":
        return _print_command_version(argv[0])

    parser: argparse.ArgumentParser = lib.buildargs()
    args: Namespace
    remaining_argv: list
    args, remaining_argv = parser.parse_known_args(argv)

    # Auto-detect the default token-file path (``$XDG_RUNTIME_DIR/bed.token``
    # or ``/tmp/bed-<uid>/bed.token``) when the operator did not pass
    # ``--token-file`` explicitly. If the resolved file is empty,
    # clear ``args.token_file`` so the ``if args.token_file:`` check
    # in :meth:`CasinoClient.run` and :func:`casino.auth.connect`
    # cleanly falls through to the prompt path.
    from casino.auth import _resolve_token_file

    _resolve_token_file(args)

    if getattr(args, "install", False):
        return _run_install(args)

    if getattr(args, "install_test_data", False) or getattr(args, "uninstall_test_data", False):
        return _run_test_data(args)

    if getattr(args, "cleanup_test_state", False):
        return _run_cleanup_test_state(args)

    if getattr(args, "install_opencode", False) or getattr(args, "uninstall_opencode", False):
        return _run_opencode(args)

    if remaining_argv and remaining_argv[0] in _COMMAND_PACKAGES:
        return _run_command(remaining_argv[0], args, remaining_argv[1:])

    _routing.select_backend(args)
    return _run_bed(args)


def poker_main(argv: list[str] | None = None) -> int:
    """Thin entry point for the ``poker`` console-script.

    Equivalent to invoking ``casino poker [...argv]``, which connects through
    bed and runs the poker command package.
    """
    return main(["poker", *(argv if argv is not None else sys.argv[1:])])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BedNotReachable:
        io.echo_traceback("casino")
        raise SystemExit(1) from None
