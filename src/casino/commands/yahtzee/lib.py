# commands/yahtzee/lib.py
# Yahtzee command functions. Mirrors commands/slots/lib.py.
#
# Routing:
#   Yahtzee plays through bed. ``play()`` dispatches to ``yahtzee/game.py``,
#   which handles ``yahtzee_quick_play`` on the BED-side flow. There is no
#   door-mode route.
#
# Help wiring:
#   Every interactive prompt passes a help= callback so KEY_HELP / KEY_F1
#   redraws the prompt's option list. Each callback calls util.heading()
#   exactly once per display of help (one F1 press -> one heading).

from bbsengine6 import io, module, util
from casino import host


def play(args, **kwargs) -> bool:
    """Start a yahtzee session through the bed-side game module."""
    return module.run(args, "game", package="casino.yahtzee", **kwargs)


def _render_help(**kwargs) -> None:
    """F1/HELP callback for the yahtzee submenu.

    Per the spec: util.heading() is called exactly once per display of
    help, then the option list is echoed.

    Note: the yahtzee submenu has no seat-gated options — ``[P]lay``
    routes to ``yahtzee_quick_play`` which lazy-creates the player's
    hidden yahtzee table and auto-seats them
    (``yahtzee/api_handler.py:_handle_message``); ``[Q]uit`` is
    unconditional. So unlike the slots submenu and the main
    ``casino_client`` menu, no visibility filter is needed here.
    """
    util.heading("Yahtzee")
    io.echo("{var:optioncolor}[P]{var:labelcolor}lay a yahtzee session")
    io.echo("{var:optioncolor}[Q]{var:labelcolor}uit to main menu")


def menu(args, **kwargs):
    """Show the yahtzee submenu and dispatch the chosen subcommand."""
    util.heading("Yahtzee")
    _render_help()
    # host.choose: LO when hosted, io.inputchoice standalone. Uppercased for the checks below.
    cmd = (host.choose(
        "{var:promptcolor}[P]lay  [Q]uit: {var:inputcolor}",
        "p,q",
        default="q",
        help=_render_help,
    ) or "").upper()

    if cmd == "P":
        play(args, **kwargs)

    return True
