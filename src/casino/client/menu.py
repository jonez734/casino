# casino/client/menu.py
# Interactive main menu for CasinoClient.

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsengine6 import io, util

from ..menu_lib import MenuOption, visible_options
from .registry import get_client

if TYPE_CHECKING:
    from .casino_client import CasinoClient


# Each ``MenuOption`` declares visibility gates via ``requires_seated``,
# ``allowed_game_types`` (combined with ``requires_seated``), and
# ``requires_connected``. The runtime filter lives in
# :func:`casino.menu_lib.visible_options`; this file is the static
# spec plus the rendering loop.
_OPTIONS_SPEC = (
    MenuOption("t", "Tables  (list open tables)",     requires_seated=False),
    MenuOption("c", "Create  (create a new table)",   requires_seated=False),
    MenuOption("u", "Update  (modify an existing table)", requires_seated=False),
    MenuOption("j", "Join Table",                     requires_seated=False),
    MenuOption("l", "Leave   (leave current table)",  requires_seated=True),
    MenuOption("b", "Bet     (place a wager)",         requires_seated=True, allowed_game_types=frozenset({"blackjack", "poker"})),
    MenuOption("h", "Hit     (take another card)",     requires_seated=True, allowed_game_types=frozenset({"blackjack"})),
    MenuOption("s", "Stand   (hold your hand)",        requires_seated=True, allowed_game_types=frozenset({"blackjack"})),
    MenuOption("m", "Message (send chat)",             requires_seated=False),
    MenuOption("k", "Bank    (open the bank submenu)", requires_seated=False),
    MenuOption("x", "TicTac (quick-play tictactoe)",  requires_seated=False),
    MenuOption("v", "Move   (tictactoe cell 0-8)",    requires_seated=True, allowed_game_types=frozenset({"tictactoe"})),
    MenuOption("n", "Join   (join tictactoe as 'O')",    requires_seated=True, allowed_game_types=frozenset({"tictactoe"})),
    MenuOption("g", "Resign (forfeit tictactoe)",     requires_seated=True, allowed_game_types=frozenset({"tictactoe"})),
    MenuOption("q", "uit",                            requires_seated=False),
)
_DEFAULT = "q"


def _visible_options(client: "CasinoClient | None"):
    """Yield ``(letter, label)`` tuples the client may currently pick.

    Thin shim around :func:`casino.menu_lib.visible_options`. Kept so
    callers (including tests) that import ``_visible_options`` from
    this module keep working unchanged.
    """
    return [
        (opt.letter, opt.label)
        for opt in visible_options(_OPTIONS_SPEC, client)
    ]


def _render_help(client: "CasinoClient | None" = None, **kwargs) -> None:
    """F1/HELP callback for the casino_client main menu.

    Per the spec: ``util.heading()`` is called exactly once per display
    of help, then the option list is echoed. Only currently-visible
    options are listed so the help screen matches the prompt.
    """
    client = client or get_client()
    util.heading("casino_client")
    for letter, label in _visible_options(client):
        # f-string ``{{`` collapses to literal ``{`` so ``io.echo``
        # sees ``{var:optioncolor}`` / ``{var:labelcolor}`` markup.
        io.echo(
            f"{{var:optioncolor}}[{letter.upper()}]{{var:labelcolor}} {label}"
        )


def menu(client: "CasinoClient | None" = None, **kwargs) -> str | None:
    """Show the casino_client main menu and return the chosen command.

    The status prefix (``[moniker] Balance: X [Table: Y]``) is echoed
    inline above the option list so the operator sees balance and
    current table on every keystroke; the literal ``casino_client: ``
    text remains the final prompt. KEY_HELP / KEY_F1 re-renders the
    heading + option list via :func:`_render_help`.

    The visible option set is filtered by the player's joined-table
    state and game type so options the server would reject (e.g.
    ``[B]et`` outside blackjack/poker) never appear. Quit (``[Q]``)
    is always present, so ``default="q"`` remains valid in every state.

    Args:
        client: explicit CasinoClient; falls back to the active
            registry client (``client.registry.get_client()``) when
            None, mirroring ``commands/slots/lib.py:menu``.

    Returns:
        Uppercase command letter, or None if the user aborted.
    """
    client = client or get_client()
    visible = _visible_options(client)
    option_str = ",".join(letter for letter, _label in visible)
    status = (
        f"{{var:promptcolor}}[{client.moniker}] Balance: {client.balance}"
        + (
            f" Table: {client.current_table_moniker}"
            if client and client.current_table_moniker
            else ""
        )
        + "{f6}"
    )
    inline = "{f6}".join(
        # f-string ``{{`` collapses to literal ``{`` so ``io.echo``
        # sees ``{var:optioncolor}`` / ``{var:labelcolor}`` markup.
        # ``{f6}`` between options puts each entry on its own line so
        # the long option list is readable instead of one horizontal
        # wall of ``[T]ables,[C]reate,...``.
        f"{{var:optioncolor}}[{letter.upper()}]{{var:labelcolor}} {label}"
        for letter, label in visible
    )
    prompt = status + inline + "{f6}{var:promptcolor}casino_client: {var:inputcolor}"
    return io.inputchoice(
        prompt,
        option_str,
        default=_DEFAULT,
        help=_render_help,
    )
