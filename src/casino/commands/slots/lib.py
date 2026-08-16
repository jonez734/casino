# commands/slots/lib.py
# Slots command functions. Mirrors commands/blackjack/lib.py.
#
# Help wiring:
#   Every interactive prompt passes a help= callback so KEY_HELP / KEY_F1
#   redraws the prompt's option list. Each callback calls util.heading()
#   exactly once per display of help (one F1 press -> one heading).

from bbsengine6 import io, util


def play(args, **kwargs) -> bool:
    """Start a local slots session."""
    from bbsengine6 import module

    return module.run(args, "game", package="casino.slots", **kwargs)


def _render_help(**kwargs) -> None:
    """F1/HELP callback for the slots submenu.

    Per the spec: util.heading() is called exactly once per display of
    help, then the option list is echoed.
    """
    util.heading("Slots")
    io.echo("{var:optioncolor}[P]{var:labelcolor}lay a slot session")
    io.echo("{var:optioncolor}[Q]{var:labelcolor}uit to main menu")


def menu(args, **kwargs):
    """Show the slots submenu and dispatch the chosen subcommand."""
    util.heading("Slots")
    _render_help()
    cmd = io.inputchoice(
        "{var:promptcolor}[P]lay  [Q]uit: {var:inputcolor}",
        "p,q",
        default="q",
        help=_render_help,
    )

    if cmd == "P":
        play(args, **kwargs)

    return True
