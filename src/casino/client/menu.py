# casino/client/menu.py
# Interactive main menu for CasinoClient.

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsengine6 import io, util

from .registry import get_client

if TYPE_CHECKING:
    from .casino_client import CasinoClient


# Each entry: (letter, inline_short, long_label, requires_seated, allowed_game_types).
# ``allowed_game_types`` is a frozenset of game types for which this option
# is meaningful; ``None`` means "any type" (or "type doesn't matter").
# Visibility is computed at runtime from ``client.current_table_moniker``
# and ``client.current_table_game_type``; the spec is the static source
# of truth so the prompt and F1/HELP stay in lock-step.
_OPTIONS_SPEC = (
    ("t", "ables",  "ables (list open tables)",      False, None),
    ("c", "reate",  "reate a new table",             False, None),
    ("u", "pdate",  "pdate an existing table",       False, None),
    ("j", "oin",    "oin a table",                   False, None),
    ("l", "eave",   "eave the current table",        True,  None),
    ("b", "et",     "et (place a wager)",            True,  frozenset({"blackjack", "poker"})),
    ("h", "it",     "it (take another card)",        True,  frozenset({"blackjack"})),
    ("s", "tand",   "tand (hold your hand)",         True,  frozenset({"blackjack"})),
    ("m", "sg",     "sg (send chat)",                False, None),
    ("k", "ank",    "ank (open the bank submenu)",   False, None),
    ("x", "TicTac", "TicTac (quick-play tictactoe)", False, None),
    ("v", "Move",   "Move (tictactoe cell 0-8)",     True,  frozenset({"tictactoe"})),
    ("n", "JoinT",  "JoinT (join tictactoe as O)",   True,  frozenset({"tictactoe"})),
    ("g", "Resign", "Resign (forfeit tictactoe)",    True,  frozenset({"tictactoe"})),
    ("q", "uit",    "uit",                           False, None),
)
_DEFAULT = "q"


def _visible_options(client: "CasinoClient | None"):
    """Yield ``(letter, short, long_)`` tuples the client may currently pick.

    ``needs_seated`` options are skipped when no table is joined.
    ``allowed_game_types``-constrained options are skipped when the
    seated table's game type is unknown or outside the allowed set;
    this also covers the brief window between ``join_table`` and the
    first ``game_state`` reply, when ``current_table_game_type`` is
    still ``None``.
    """
    seated = bool(client and client.current_table_moniker)
    gt = (getattr(client, "current_table_game_type", None) or "").strip() or None
    for letter, short, long_, needs_seat, types in _OPTIONS_SPEC:
        if needs_seat and not seated:
            continue
        if needs_seat and types and gt not in types:
            continue
        yield (letter, short, long_)


def _render_help(client: "CasinoClient | None" = None, **kwargs) -> None:
    """F1/HELP callback for the casino_client main menu.

    Per the spec: ``util.heading()`` is called exactly once per display
    of help, then the option list is echoed. Only currently-visible
    options are listed so the help screen matches the prompt.
    """
    client = client or get_client()
    util.heading("casino_client")
    for letter, _short, long_ in _visible_options(client):
        # f-string ``{{`` collapses to literal ``{`` so ``io.echo``
        # sees ``{var:optioncolor}`` / ``{var:labelcolor}`` markup.
        io.echo(
            f"{{var:optioncolor}}[{letter.upper()}]{{var:labelcolor}}{long_}"
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
    visible = list(_visible_options(client))
    option_str = ",".join(letter for letter, _short, _long in visible)
    status = (
        f"{{var:promptcolor}}[{client.moniker}] Balance: {client.balance}"
        + (
            f" Table: {client.current_table_moniker}"
            if client and client.current_table_moniker
            else ""
        )
    )
    inline = "".join(
        # f-string ``{{`` collapses to literal ``{`` so ``io.echo``
        # sees ``{var:optioncolor}`` / ``{var:labelcolor}`` markup.
        f"{{var:optioncolor}}[{letter.upper()}]{{var:labelcolor}}{short}"
        for letter, short, _long in visible
    )
    prompt = status + inline + "{var:promptcolor}casino_client: {var:inputcolor}"
    return io.inputchoice(
        prompt,
        option_str,
        default=_DEFAULT,
        help=_render_help,
    )
