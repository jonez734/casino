# casino/yahtzee/__main__.py
# Yahtzee subpackage entry point.
#
# Mirrors casino/blackjack/__main__.py. Boots the BBS session, sets
# up the terminal, then dispatches based on --mode:
#
# - --mode human (default): interactive door-mode play loop, dispatched
#   through bbsengine6.module.run("game", package="casino.yahtzee").
# - --mode auto: zero-player, the house plays a full 13-round game
#   with greedy scoring (lib.greedy_locks + lib.greedy_best_category),
#   no member lookup required, useful for stress-testing the score
#   engine from the command line.

import locale
import sys
import time

from bbsengine6 import io, module, screen, session
from bbsengine6.net.ping import PingUnavailable

from . import lib
from . import play as yahtzee_play

def main(argv: list[str] | None = None) -> int:
    parser = lib.buildargs()
    args = parser.parse_args() if parser is not None else None

    is_auto = getattr(args, "mode", "human") == "auto"

    if not is_auto:
        session.start(args)
        screen.init()
        locale.setlocale(locale.LC_ALL, "")
        time.tzset()

    try:
        if is_auto:
            yahtzee_play.auto_main(args)
        else:
            module.run(args, "game", package="casino.yahtzee")
    except KeyboardInterrupt:
        io.echo("{/all}{bold}INTR{/bold}")
    except EOFError:
        io.echo("{/all}{bold}EOF{/bold}")
    except PingUnavailable as exc:
        io.echo_traceback("casino.yahtzee")
        return 1
    finally:
        if not is_auto:
            io.echo(
                f"{{decsc}}{{curpos:{io.terminal.height()},0}}"
                "{el}{reset}{decrc}{/all}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
