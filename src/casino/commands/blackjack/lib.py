# commands/blackjack/lib.py
# Blackjack command functions

from bbsengine6 import io


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

    cmd = io.inputchoice(
        "{var:promptcolor}[P]lay  [Q]uit: {var:inputcolor}",
        "p,q",
        default="q",
    )

    if cmd == "P":
        play(args, **kwargs)

    return True
