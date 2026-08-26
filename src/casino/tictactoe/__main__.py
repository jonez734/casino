# casino/tictactoe/__main__.py
# Tictactoe subpackage entry point.
#
# Standalone door-mode driver. Boots a BBS session against the local
# Postgres pool (mirroring casino/__main__.py:_run_direct), then runs a
# single tic-tac-toe game in one of two modes:
#
# - Mode 0 (zero-player): two AI play to completion. Each move is
#   echoed to the terminal; the final tictactoe_result is printed.
#   With perfect play on both sides this always ends in a draw.
#
# - Mode 1 (single-player): one human (X) vs the AI (O). The human
#   is prompted for a cell 0-8 after each AI reply (and at the start
#   of the game). Resigning forfeits.
#
# The BED surface remains the primary v1 entry point
# (casino.tictactoe.api_handler / MessageRouter), so this launcher is
# the canonical "play a quick game without the bed daemon" path.
#
# The merged ``casino`` CLI's --direct branch uses this same skeleton
# (database.getpool + session.start(args, pool=pool)) so the two
# surfaces stay in sync.

import argparse
import locale
import sys
import time
from argparse import Namespace

from bbsengine6 import database, io, member, module, screen, session
from bbsengine6.net.ping import PingUnavailable

from . import lib
from .service import TictactoeService

PROMPT_OPTIONS = "0123456789QR"


def buildargs() -> argparse.ArgumentParser:
    from casino import lib as casino_lib
    parser = casino_lib.buildargs()
    parser.add_argument(
        "--mode",
        type=int,
        choices=(0, 1),
        default=1,
        help=(
            "0 = zero-player (2 AI self-play); "
            "1 = single-player (human X vs AI O). Default 1."
        ),
    )
    return parser


def _render_state(state: dict) -> None:
    board = lib.Board(
        cells=tuple(state["board"]),
        to_move=state["to_move"],
        winner=state.get("winner"),
    )
    io.echo(board.render())
    last = state.get("last_move")
    if last and last.get("by") and not last.get("resigned"):
        io.echo(
            f"{{var:labelcolor}}last move:{{var:valuecolor}} "
            f"cell {last.get('cell')} by {last.get('by')}"
        )
    if state.get("turn_moniker"):
        io.echo(
            f"{{var:labelcolor}}turn:{{var:valuecolor}} {state['turn_moniker']}"
        )


def _render_result(result: dict) -> None:
    board = lib.Board(
        cells=tuple(result["board"]),
        to_move=1,
        winner=result.get("winner"),
    )
    io.echo(board.render())
    if result.get("is_draw"):
        io.echo("{level.ok}draw -- bet pushed{/all}")
    else:
        winner_moniker = result.get("winner_moniker") or "?"
        io.echo(f"{{level.ok}}winner: {winner_moniker}{{/all}}")
    io.echo(f"{{var:labelcolor}}moves played:{{var:valuecolor}} {result['moves_played']}")
    io.echo(f"{{var:labelcolor}}payout:{{var:valuecolor}} {result['payout']}")
    if result.get("new_balance"):
        io.echo(f"{{var:labelcolor}}new balance:{{var:valuecolor}} {result['new_balance']}")


def _run_mode0(svc: TictactoeService, player_moniker: str) -> int:
    initial = svc.quick_play(player_moniker, mode=0)
    if initial.get("type") == "error":
        io.echo(f"{{level.error}}{initial.get('message')}{{/all}}")
        return 1
    io.echo("{{var:titlecolor}}tic-tac-toe (mode 0: AI vs AI){{/all}}")
    states = svc.auto_play_mode0(initial["table_moniker"])
    for state in states:
        if state.get("type") == "tictactoe_state":
            io.echo("{f6}")
            _render_state(state)
        elif state.get("type") == "tictactoe_result":
            io.echo("{f6}")
            _render_result(state)
        else:
            io.echo(f"{{level.error}}{state}{{/all}}")
    return 0


def _run_mode1(svc: TictactoeService, player_moniker: str) -> int:
    state = svc.quick_play(player_moniker, mode=1)
    if state.get("type") == "error":
        io.echo(f"{{level.error}}{state.get('message')}{{/all}}")
        return 1
    io.echo("{{var:titlecolor}}tic-tac-toe (mode 1: you vs AI){{/all}}")
    io.echo("{var:labelcolor}you are X. enter a cell 0-8 (top-left = 0, bottom-right = 8).{/all}")
    table_moniker = state["table_moniker"]

    while True:
        if state.get("type") == "tictactoe_result":
            io.echo("{f6}")
            _render_result(state)
            return 0
        if state.get("type") == "error":
            io.echo(f"{{level.error}}{state.get('message')}{{/all}}")
            return 1

        io.echo("{f6}")
        _render_state(state)

        if state.get("turn_moniker") != player_moniker:
            return 0

        raw = io.inputchoice(
            options=PROMPT_OPTIONS,
            prompt="{var:promptcolor}your move {var:optioncolor}[0-8] Q R{var:promptcolor}: {var:inputcolor}",
            default=None,
            clearline=False,
        )
        if raw is None:
            continue
        answer = str(raw).strip().upper()
        if answer == "Q":
            return 0
        if answer == "R":
            state = svc.resign(table_moniker, player_moniker)
            continue
        try:
            cell = int(answer)
        except ValueError:
            io.echo("{level.error}enter a digit 0-8, q to quit, or r to resign{/all}")
            continue
        state = svc.play_move(table_moniker, player_moniker, cell)


def main(argv: list[str] | None = None) -> int:
    parser = buildargs()
    args: Namespace = parser.parse_args(argv)

    if module.run(args, "startup", package="bbsengine6") is False:
        io.echo("bbsengine6 startup failed")
        return 1

    try:
        with database.getpool(args, database=args.databasename) as pool:
            session.start(args, pool=pool)

            player_moniker = member.getcurrentid(args, pool=pool)
            if not player_moniker:
                io.echo("{level.error}Could not determine current member.{/all}")
                return 1

            screen.init()
            locale.setlocale(locale.LC_ALL, "")
            time.tzset()

            svc = TictactoeService(args, pool=pool)
            try:
                if args.mode == 0:
                    rc = _run_mode0(svc, player_moniker)
                else:
                    rc = _run_mode1(svc, player_moniker)
            except KeyboardInterrupt:
                io.echo("{/all}{bold}INTR{/bold}")
                rc = 130
            except EOFError:
                io.echo("{/all}{bold}EOF{/bold}")
                rc = 130
            except PingUnavailable:
                io.echo_traceback("casino.tictactoe")
                rc = 1
            finally:
                io.echo(
                    f"{{decsc}}{{curpos:{io.terminal.height()},0}}"
                    "{el}{reset}{decrc}{/all}"
                )
            return rc
    except KeyboardInterrupt:
        io.echo("{/all}{bold}INTR{/bold}")
        return 130


if __name__ == "__main__":
    sys.exit(main())
