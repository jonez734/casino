from __future__ import annotations

import argparse
from argparse import Namespace

from bbsengine6 import io, util, member, database, session

from . import lib
from . import _version
from . import connect


def parse_module_path(path: str) -> tuple[str, str | None]:
    """Parse 'module.subcommand' or 'module' into separate parts.

    Args:
        path: Module path like 'table.list' or 'connect'

    Returns:
        Tuple of (module, subcommand) where subcommand may be None
    """
    if "." in path:
        module, subcommand = path.rsplit(".", 1)
        return module, subcommand
    return path, None


def init(args: Namespace, **kwargs) -> bool:
    return True


def access(args: Namespace, op: str, **kwargs) -> bool:
    return True


def buildargs(args, **kwargs):
    if hasattr(args, "add_argument"):
        args.add_argument(
            "--host",
            dest="host",
            default="localhost",
            help="Casino server host (default: localhost)",
        )
        args.add_argument(
            "--port",
            dest="port",
            type=int,
            default=8765,
            help="Casino server port (default: 8765)",
        )
    else:
        if not hasattr(args, "host"):
            args.host = "localhost"
        if not hasattr(args, "port"):
            args.port = 8765


def main(args: Namespace, **kwargs) -> bool:
    if args.debug is True:
        io.echo(f"casino.main.100: {args=}", level="debug")

    io.echo(f"casino.main.100: {kwargs.get('pool')=}", level="debug")

    remote_client = None

    options = (
        ("B", "Blackjack", "blackjack.play"),
        ("P", "Poker", "poker.play"),
        ("S", "Slots", "slots.play"),
        ("Y", "Yahtzee", "yahtzee.play"),
        ("C", "Connect", "connect"),
        ("L", "List tables", "table.list"),
        ("J", "Join table", "table.join"),
        ("V", "View table", "table.view"),
        ("W", "Watch table", "admin.watch"),
        ("U", "Unwatch table", "admin.unwatch"),
        ("A", "Bet", "game.bet"),
        ("H", "Hit", "game.hit"),
        ("T", "Stand", "game.stand"),
        ("P", "Play", "game.play"),
        ("G", "Global msg", "chat.global"),
        ("K", "Bank", "bank"),
        ("X", "Disconnect", "connect.disconnect"),
        ("M", "Maintenance", "maint.main"),
    )

    def mainmenuhelp(**kwargs):
        for o in options:
            opt = o[0]
            t = o[1]
            _callback = o[2]
            io.echo(
                f"{{/all}}{{optioncolor}}[{opt}]{{/all}} {{valuecolor}} {t}{{/all}}"
            )
        io.echo("{F6}{optioncolor}[Q]{/all}{valuecolor} Quit :door:{/all}")

    io.echo(f"casino.main.400: {args=} {kwargs=}")
    util.heading("casino")

    connect.init_remote_client_screen()

    io.echo(
        f"database: {args.databasename} host: {args.databasehost}:{args.databaseport}",
        level="debug",
    )

    if lib.runmodule(args, "startup", **kwargs) is False:
        io.echo("casino failed to start up", level="critical")
        return False

    try:
        with database.getpool(args, dbname=args.databasename) as pool:
            if session.start(args, pool=pool) is False:
                io.echo("casino.main.240: session.start() failed", level="error")
                return False

            lib.setbottombar(
                args,
                f"casino {_version.datestamp} githash {_version.githash}",
                player=None,
                pool=pool,
            )

            currentmembermoniker = member.getcurrentmoniker(args, pool=pool)
            io.echo(f"main.300: {currentmembermoniker=}", level="debug")
            if currentmembermoniker is False:
                io.echo("casino.main.200: you do not exist! go away!", level="error")
                return False

            currentplayer = lib.CasinoPlayer(
                args, membermoniker=currentmembermoniker, pool=pool
            )
            if currentplayer is None:
                io.echo("casino.main.220: no player selected", level="info")
                return True

            done = False
            while not done:
                lib.setbottombar(
                    args,
                    f"casino {_version.datestamp} git {_version.githash}",
                    player=currentplayer,
                    pool=pool,
                )

                util.heading("main menu")

                io.echo()

                choices = "QX"
                for o in options:
                    choices += o[0]
                mainmenuhelp()

                try:
                    ch = io.inputchoice(
                        f"{{var:promptcolor}}Your command, {currentplayer.moniker}? {{var:inputcolor}}",
                        choices,
                        "",
                        help=mainmenuhelp,
                        **kwargs,
                    )

                    if ch == "Q" or ch == "X":
                        if remote_client is not None:
                            connect.disconnect(args, client=remote_client)
                            connect.cleanup_remote_client_screen()
                        io.echo(":door: {optioncolor}Q{labelcolor} -- quit game{/all}")
                        done = True
                        break
                    else:
                        for o in options:
                            if o[0] != ch:
                                continue
                            option = o[0]
                            title = o[1]
                            module_path = o[2]
                            module, subcommand = parse_module_path(module_path)
                            io.echo(
                                f"{{optioncolor}}{option}{{normalcolor}} -- {title}{{/all}}"
                            )

                            run_kwargs = dict(kwargs)
                            run_kwargs["player"] = currentplayer
                            run_kwargs["pool"] = pool
                            run_kwargs["client"] = remote_client
                            if subcommand is not None:
                                run_kwargs["subcommand"] = subcommand

                            res = lib.runmodule(args, module, **run_kwargs)

                            if module == "connect" and subcommand is None:
                                remote_client = res
                            elif res is not True:
                                io.echo(
                                    f"error running submodule {module_path}, returned {res=}",
                                    level="error",
                                )
                            io.echo()
                            break
                except EOFError:
                    io.echo("{/all}*EOF*")
                    return True
                except KeyboardInterrupt:
                    io.echo("{/all}*INTR*")
                    return True

            currentplayer.save()
    finally:
        lib._unregister_casino_fragments()
    return True
