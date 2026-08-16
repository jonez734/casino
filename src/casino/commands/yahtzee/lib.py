# commands/yahtzee/lib.py
# Yahtzee command functions. Mirrors commands/slots/lib.py.
#
# Routing:
#   Yahtzee is the only casino game where the BED-side flow is the
#   primary path. The default dispatch from ``play()`` lands in
#   ``yahtzee/game.py`` (the BED-side module that handles
#   ``yahtzee_quick_play``). A thin door-mode wrapper is also
#   exposed for callers that pass ``--direct``; in that case
#   ``play()`` routes to ``yahtzee/play.py``.
#
# Help wiring:
#   Every interactive prompt passes a help= callback so KEY_HELP / KEY_F1
#   redraws the prompt's option list. Each callback calls util.heading()
#   exactly once per display of help (one F1 press -> one heading).

from bbsengine6 import io, module, util


def play(args, **kwargs) -> bool:
    """Start a yahtzee session.

    Dispatches to the door-mode play module when ``args.direct`` is
    True (the --direct flag, useful for offline play); otherwise
    dispatches to the game module which handles the BED-side flow.
    """
    if getattr(args, "direct", False):
        return module.run(args, "play", package="casino.yahtzee", **kwargs)
    return module.run(args, "game", package="casino.yahtzee", **kwargs)


def _render_help(**kwargs) -> None:
    """F1/HELP callback for the yahtzee submenu.

    Per the spec: util.heading() is called exactly once per display of
    help, then the option list is echoed.
    """
    util.heading("Yahtzee")
    io.echo("{var:optioncolor}[P]{var:labelcolor}lay a yahtzee session")
    io.echo("{var:optioncolor}[Q]{var:labelcolor}uit to main menu")


def menu(args, **kwargs):
    """Show the yahtzee submenu and dispatch the chosen subcommand."""
    util.heading("Yahtzee")
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
