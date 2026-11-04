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
    io.echo("  [X] Exit   return to the main menu")
    io.echo()

    # host.choose: LO when hosted, io.inputchoice standalone. Uppercased for the checks below.
    cmd = (host.choose(
        "{var:promptcolor}[P]lay  [X] Exit: {var:inputcolor}",
        "p,x",
        default="x",
    ) or "").upper()
    if cmd == "Q":  # Q is the BC alias of X
        cmd = "X"

    if cmd == "P":
        play(args, **kwargs)

    return True
