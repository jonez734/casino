# casino/yahtzee/__main__.py
# Yahtzee subpackage entry point.
#
# Runs --mode auto: zero-player, the house plays a full 13-round game with
# greedy scoring (lib.greedy_locks + lib.greedy_best_category). No member
# lookup and no database, so it is useful for stress-testing the score
# engine from the command line. Play against the bed is through
# ``casino yahtzee``; this module has no interactive play loop.

import sys

from bbsengine6 import io
from bbsengine6.net.ping import PingUnavailable

from . import lib
from . import play as yahtzee_play


def main(argv: list[str] | None = None) -> int:
    parser = lib.buildargs()
    args = parser.parse_args(argv) if parser is not None else None

    try:
        yahtzee_play.auto_main(args)
    except KeyboardInterrupt:
        io.echo("{/all}{bold}INTR{/bold}")
    except EOFError:
        io.echo("{/all}{bold}EOF{/bold}")
    except PingUnavailable:
        io.echo_traceback("casino.yahtzee")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
