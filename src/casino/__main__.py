# casino/__main__.py
# Entry point for the merged ``casino`` CLI.
#
# Three branches:
#
# - ``casino blackjack [...]``: door-mode blackjack, dispatched through
#   the merged entry point. Short-circuits before any backend probe
#   because blackjack has no bed counterpart -- it talks to the local
#   Postgres pool via ``bbsengine6.database``. The standalone
#   ``python -m casino.blackjack`` entry and the ``bin/blackjack`` shim
#   continue to work; this branch is purely additive.
#
# - ``casino --direct`` (or no ``--direct`` but bed unreachable --
#   operator reruns with ``--direct``): door mode. Opens a Postgres
#   connection pool via ``bbsengine6.database``, starts a BBS session,
#   and runs the interactive door menu (``casino.main``). Mirrors the
#   pre-merge ``casino`` shim's behavior.
#
# - default: bed WebSocket client. Probes the bed daemon on
#   ``--bed-host/--bed-port``; if reachable, instantiates
#   ``CasinoClient`` and runs the terminal UI loop. If unreachable and
#   ``--direct`` was not set, re-raises
#   :class:`bed.tools._routing.BedNotReachable` so the operator gets
#   the bundled "rerun with --direct" hint.
#
# Subcommand detection runs before backend selection so that
# ``casino blackjack`` never blocks on a (possibly unreachable) bed
# daemon. Selection is delegated to :func:`casino._routing.select_backend`
# for the door/bed branches, which mirrors the convention used by every
# tool under ``bed.tools``.

from __future__ import annotations

import argparse
import locale
import sys
import time
from argparse import Namespace

from bbsengine6 import database, io, screen, session
from bbsengine6.io import screen as io_screen
from bed.tools._routing import BedNotReachable

from . import _routing, lib
from .blackjack import lib as blackjack_lib
from .client import CasinoClient


def _run_direct(args: Namespace, remaining_argv: list) -> int:
    """Door-mode branch: open a DB pool, start a BBS session, run menu."""
    if lib.runmodule(args, "startup", package="bbsengine6") is False:
        io.echo("bbsengine6 startup failed")
        return 1

    with database.getpool(args, database=args.databasename) as pool:
        session.start(args, pool=pool)

    screen.init()

    locale.setlocale(locale.LC_ALL, "")
    time.tzset()

    try:
        lib.runmodule(args, "main", argv=remaining_argv)
    except KeyboardInterrupt:
        io.echo("{/all}{bold}INTR{/bold}")
    except EOFError:
        io.echo("{/all}{bold}EOF{/bold}")
    finally:
        io.echo(f"{{savecursor}}{{curpos:{io.terminal.height()},0}}"
                f"{{el}}{{reset}}{{restorecursor}}")
    return 0


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
    return 0 if getattr(client, "authenticated", False) else 1


def _run_blackjack(args: Namespace, remaining_argv: list) -> int:
    """``casino blackjack [...]`` branch: door-mode blackjack."""
    from bbsengine6 import module

    bj_args = blackjack_lib.buildargs().parse_args(remaining_argv)

    session.start(bj_args)

    io_screen.init()

    locale.setlocale(locale.LC_ALL, "")
    time.tzset()

    try:
        module.run(bj_args, "game", package="casino.blackjack")
    except KeyboardInterrupt:
        io.echo("{/all}{bold}INTR{bold}")
    except EOFError:
        io.echo("{/all}{bold}EOF{bold}")
    finally:
        io.echo(f"{{savecursor}}{{curpos:{io.terminal.height()},0}}"
                f"{{el}}{{reset}}{{restorecursor}}")
    return 0


_BLACKJACK_SUBCOMMAND = "blackjack"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # Route ``casino blackjack --help`` to the blackjack parser so the
    # operator sees blackjack-specific flags (``--databasename`` etc.)
    # rather than the bed/database flag set of the top-level parser.
    # Without this, the top-level parser's ``--help`` action exits the
    # process before the subcommand short-circuit gets a chance to
    # route.
    if argv and argv[0] == _BLACKJACK_SUBCOMMAND and \
            ("--help" in argv[1:] or "-h" in argv[1:]):
        blackjack_lib.buildargs().parse_args(argv[1:])

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

    if remaining_argv and remaining_argv[0] == _BLACKJACK_SUBCOMMAND:
        return _run_blackjack(args, remaining_argv[1:])

    backend = _routing.select_backend(args)

    if backend == "direct":
        return _run_direct(args, remaining_argv)
    return _run_bed(args)


def blackjack_main(argv: list[str] | None = None) -> int:
    """Thin entry point for the ``blackjack`` console-script.

    Equivalent to invoking ``casino blackjack [...argv]``.
    """
    return main([_BLACKJACK_SUBCOMMAND, *(argv if argv is not None else sys.argv[1:])])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BedNotReachable:
        io.echo_traceback("casino")
        raise SystemExit(1) from None
