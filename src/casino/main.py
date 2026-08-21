from argparse import Namespace

from bbsengine6 import database, io, member, session, util

from . import _version, auth, lib
from .menu_lib import MenuOption, visible_options


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


def init(args: Namespace, **kwargs) -> bool | None:
    return True


def access(args: Namespace, op: str, **kwargs) -> bool | None:
    return True


def buildargs(args, **kwargs):
    return None


def main(args: Namespace, **kwargs) -> bool | None:
    if args.debug is True:
        io.echo(f"casino.main.100: {args=}", level="debug")

    io.echo(f"casino.main.100: {kwargs.get('pool')=}", level="debug")

    remote_client = None

    # Each ``MenuOption`` carries visibility gates. The runtime filter
    # lives in :func:`casino.menu_lib.visible_options`; this file is
    # the static spec plus the rendering loop.
    options = (
        # ---- Always available ----
        MenuOption("c", "Connect",       "auth",            requires_seated=False),
        MenuOption("l", "List tables",   "table.list",      requires_seated=False),
        MenuOption("j", "Join table",    "table.join",      requires_seated=False),
        MenuOption("v", "View table",    "table.view",      requires_seated=False),
        MenuOption("w", "Watch table",   "admin.watch",     requires_seated=False),
        MenuOption("u", "Unwatch table", "admin.unwatch",   requires_seated=False),
        MenuOption("g", "Global msg",    "chat.global",     requires_seated=False),
        MenuOption("k", "Bank",          "bank",            requires_seated=False),
        MenuOption("x", "Disconnect",    "auth.disconnect", requires_seated=False, requires_connected=True),
        MenuOption("m", "Maintenance",   "maint.main",      requires_seated=False),
        # ---- Seat-gated game actions ----
        # Bet applies to blackjack and poker; Hit/Stand are bj-only.
        MenuOption("a", "Bet",     "game.bet",   requires_seated=True, allowed_game_types=frozenset({"blackjack", "poker"})),
        MenuOption("h", "Hit",     "game.hit",   requires_seated=True, allowed_game_types=frozenset({"blackjack"})),
        MenuOption("t", "Stand",   "game.stand", requires_seated=True, allowed_game_types=frozenset({"blackjack"})),
        MenuOption("p", "Play",    "game.play",  requires_seated=True),
        # ---- Game launchers ----
        # Hide the launcher for the game the player is already at so the
        # same letter can't be claimed twice in the choice string.
        # Poker and Play both use ``P``; resolved via visibility (when
        # seated at a poker table, Play is the only ``P`` visible).
        MenuOption("b", "Blackjack", "blackjack.play", requires_seated=False, hide_if_seated_type=frozenset({"blackjack"})),
        MenuOption("p", "Poker",     "poker.play",     requires_seated=False, hide_if_seated_type=frozenset({"poker"})),
        MenuOption("s", "Slots",     "slots",          requires_seated=False, hide_if_seated_type=frozenset({"slots"})),
        MenuOption("y", "Yahtzee",   "yahtzee.play",   requires_seated=False, hide_if_seated_type=frozenset({"yahtzee"})),
    )

    def _menu_state(currentplayer, connected):
        """Build a duck-typed state for ``menu_lib.visible_options``.

        Combines the player's seat state (queried from the DB by
        ``CasinoPlayer._refresh_seat``) with the loop's WS-connection
        state (``remote_client is not None``) so the visibility filter
        has both pieces of information in one place.
        """
        currentplayer._refresh_seat()
        currentplayer.connected = connected
        return currentplayer

    def mainmenuhelp(**kwargs):
        """Render the main menu options.

        Per the spec: util.heading() is called exactly once per display
        of help (one F1 press -> one heading), then the option list is
        echoed. The option list is filtered through
        :func:`casino.menu_lib.visible_options` so the help screen
        matches the prompt.
        """
        util.heading("main menu")
        state = _menu_state(currentplayer, remote_client is not None)
        for opt in visible_options(options, state):
            io.echo(
                f"{{/all}}{{optioncolor}}[{opt.letter.upper()}]{{/all}} {{valuecolor}} {opt.label}{{/all}}"
            )
        io.echo("{F6}{optioncolor}[Q]{/all}{valuecolor} Quit :door:{/all}")

    io.echo(f"casino.main.400: {args=} {kwargs=}")
    util.heading("casino")

    auth.init_remote_client_screen()

    io.echo(
        f"database: {args.databasename} host: {args.databasehost}:{args.databaseport}",
        level="debug",
    )

    if lib.runmodule(args, "startup", **kwargs) is False:
        io.echo("casino failed to start up", level="critical")
        return False

    try:
        with database.getpool(args, database=args.databasename) as pool:
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

                io.echo()

                # Build the choice string from the same filtered set
                # the help screen displays. ``QX`` is always appended
                # so the player can quit from any state (matches the
                # WS-client menu's ``_DEFAULT = "q"`` invariant).
                state = _menu_state(currentplayer, remote_client is not None)
                visible_opts = visible_options(options, state)
                choices = "QX"
                for opt in visible_opts:
                    choices += opt.letter
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
                            auth.disconnect(args, client=remote_client)
                            auth.cleanup_remote_client_screen()
                        io.echo(":door: {optioncolor}Q{labelcolor} -- quit game{/all}")
                        done = True
                        break
                    else:
                        for opt in visible_opts:
                            if opt.letter != ch:
                                continue
                            letter = opt.letter
                            title = opt.label
                            module_path = opt.module_path or ""
                            module, subcommand = parse_module_path(module_path)
                            io.echo(
                                f"{{optioncolor}}{letter}{{normalcolor}} -- {title}{{/all}}"
                            )

                            run_kwargs = dict(kwargs)
                            run_kwargs["pool"] = pool
                            run_kwargs["client"] = remote_client
                            if subcommand is not None:
                                run_kwargs["subcommand"] = subcommand

                            if module == "auth" and subcommand is None:
                                res = auth.connect(args, **run_kwargs)
                            else:
                                res = lib.runmodule(args, module, package="casino.commands", **run_kwargs)

                            if module == "auth" and subcommand is None:
                                remote_client = res
                                # Track connection state for the
                                # ``requires_connected`` gate on
                                # ``[X] Disconnect``. The next loop
                                # iteration's ``_menu_state`` will pick
                                # this up.
                                if res is not None:
                                    currentplayer.connected = True
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
        lib._clear_bottombar()
    return True
