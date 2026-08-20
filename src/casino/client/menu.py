# casino/client/menu.py
# Interactive main menu for CasinoClient.

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsengine6 import io, util

from .registry import get_client

if TYPE_CHECKING:
    from .casino_client import CasinoClient


_OPTIONS = "t,c,u,j,l,b,h,s,m,k,x,v,n,g,q"
_DEFAULT = "q"


def _render_help(**kwargs) -> None:
    """F1/HELP callback for the casino_client main menu.

    Per the spec: util.heading() is called exactly once per display of
    help, then the option list is echoed.
    """
    util.heading("casino_client")
    io.echo("{var:optioncolor}[T]{var:labelcolor}ables (list open tables)")
    io.echo("{var:optioncolor}[C]{var:labelcolor}reate a new table")
    io.echo("{var:optioncolor}[U]{var:labelcolor}pdate an existing table")
    io.echo("{var:optioncolor}[J]{var:labelcolor}oin a table")
    io.echo("{var:optioncolor}[L]{var:labelcolor}eave the current table")
    io.echo("{var:optioncolor}[B]{var:labelcolor}et (place a wager)")
    io.echo("{var:optioncolor}[H]{var:labelcolor}it (take another card)")
    io.echo("{var:optioncolor}[S]{var:labelcolor}tand (hold your hand)")
    io.echo("{var:optioncolor}[M]{var:labelcolor}sg (send chat)")
    io.echo("{var:optioncolor}[K]{var:labelcolor}Bank (open the bank submenu)")
    io.echo("{var:optioncolor}[X]{var:labelcolor}TicTac (quick-play tictactoe)")
    io.echo("{var:optioncolor}[V]{var:labelcolor}Move (tictactoe cell 0-8)")
    io.echo("{var:optioncolor}[N]{var:labelcolor}JoinT (join tictactoe as O)")
    io.echo("{var:optioncolor}[G]{var:labelcolor}Resign (forfeit tictactoe)")
    io.echo("{var:optioncolor}[Q]{var:labelcolor}uit")


def menu(client: "CasinoClient | None" = None, **kwargs) -> str | None:
    """Show the casino_client main menu and return the chosen command.

    The status prefix (``[moniker] Balance: X [Table: Y]``) is echoed
    inline above the option list so the operator sees balance and
    current table on every keystroke; the literal ``casino_client: ``
    text remains the final prompt. KEY_HELP / KEY_F1 re-renders the
    heading + option list via ``_render_help``.

    Args:
        client: explicit CasinoClient; falls back to the active
            registry client (``client.registry.get_client()``) when
            None, mirroring ``commands/slots/lib.py:menu``.

    Returns:
        Uppercase command letter, or None if the user aborted.
    """
    client = client or get_client()
    status = (
        f"{{var:promptcolor}}[{client.moniker}] Balance: {client.balance}"
        + (
            f" Table: {client.current_table_moniker}"
            if client and client.current_table_moniker
            else ""
        )
    )
    prompt = (
        status
        + "{var:optioncolor}[T]{var:labelcolor}ables"
        + "{var:optioncolor}[C]{var:labelcolor}reate"
        + "{var:optioncolor}[U]{var:labelcolor}pdate"
        + "{var:optioncolor}[J]{var:labelcolor}oin"
        + "{var:optioncolor}[L]{var:labelcolor}eave"
        + "{var:optioncolor}[B]{var:labelcolor}et"
        + "{var:optioncolor}[H]{var:labelcolor}it"
        + "{var:optioncolor}[S]{var:labelcolor}tand"
        + "{var:optioncolor}[M]{var:labelcolor}sg"
        + "{var:optioncolor}[K]{var:labelcolor}Bank"
        + "{var:optioncolor}[X]{var:labelcolor}TicTac"
        + "{var:optioncolor}[V]{var:labelcolor}Move"
        + "{var:optioncolor}[N]{var:labelcolor}JoinT"
        + "{var:optioncolor}[G]{var:labelcolor}Resign"
        + "{var:optioncolor}[Q]{var:labelcolor}uit"
        + "{var:promptcolor}casino_client: {var:inputcolor}"
    )
    return io.inputchoice(
        prompt,
        _OPTIONS,
        default=_DEFAULT,
        help=_render_help,
    )
