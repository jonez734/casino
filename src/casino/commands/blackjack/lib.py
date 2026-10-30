# commands/blackjack/lib.py
# Blackjack command functions

from bbsengine6 import io
from casino import host


def play(args, **kwargs) -> bool:
    """Start a local blackjack game session."""
    from bbsengine6 import module

    return module.run(args, "game", package="casino.blackjack", **kwargs)


def menu(args, **kwargs):
    """Show blackjack subcommand help."""
    io.echo("{title}Blackjack{normal}")
    io.echo("  [P]lay   start a new blackjack session")
    io.echo("  [Q]uit   return to the main menu")
    io.echo()

    # host.choose: LO when hosted, io.inputchoice standalone. Uppercased for the checks below.
    cmd = (host.choose(
        "{var:promptcolor}[P]lay  [Q]uit: {var:inputcolor}",
        "p,q",
        default="q",
    ) or "").upper()

    if cmd == "P":
        play(args, **kwargs)

    return True
