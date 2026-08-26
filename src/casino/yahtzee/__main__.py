# casino/yahtzee/__main__.py
# Yahtzee subpackage entry point.
#
# Mirrors casino/blackjack/__main__.py. Boots the BBS session, sets
# up the terminal, then dispatches to yahtzee/game.py via
# bbsengine6.module.run.

import locale
import sys
import time

from bbsengine6 import io, module, screen, session
from bbsengine6.net.ping import PingUnavailable

from . import lib

def main(argv: list[str] | None = None) -> int:
    parser = lib.buildargs()
    args = parser.parse_args() if parser is not None else None

    session.start(args)

    screen.init()

    locale.setlocale(locale.LC_ALL, "")
    time.tzset()

    try:
        module.run(args, "game", package="casino.yahtzee")
    except KeyboardInterrupt:
        io.echo("{/all}{bold}INTR{/bold}")
    except EOFError:
        io.echo("{/all}{bold}EOF{/bold}")
    except PingUnavailable as exc:
        io.echo_traceback("casino.yahtzee")
        return 1
    finally:
        io.echo(
            f"{{decsc}}{{curpos:{io.terminal.height()},0}}{{el}}{{reset}}{{decrc}}{{/all}}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
