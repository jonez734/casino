from __future__ import annotations

import argparse
import time
import locale
from argparse import Namespace

from bbsengine6 import io, screen, session, database
from . import lib


def main() -> None:
    parser: argparse.ArgumentParser | None = lib.buildargs()
    args: Namespace | None = parser.parse_args() if parser is not None else None

    if args is not None:
        with database.getpool(args, dbname=args.databasename) as pool:
            session.start(args, pool=pool)

    screen.init()

    locale.setlocale(locale.LC_ALL, "")
    time.tzset()

    try:
        lib.runmodule(args, "main")
    except KeyboardInterrupt:
        io.echo("{/all}{bold}INTR{bold}")
    except EOFError:
        io.echo("{/all}{bold}EOF{/bold}")
    finally:
        io.echo(
            f"{{savecursor}}{{curpos:{io.terminal.height()},0}}{{el}}{{reset}}{{restorecursor}}"
        )


if __name__ == "__main__":
    main()
