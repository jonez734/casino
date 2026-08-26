# casino/tictactoe/__main__.py
# Tictactoe subpackage entry point.
#
# Mirrors casino/yahtzee/__main__.py and casino/slots/__main__.py at the
# session/screen boot level, but short-circuits before any door-mode
# dispatch: tictactoe v1 is BED-only (see tictactoe/__init__.py:main
# and tictactoe/README.md "v1 limitations"). The launcher still boots
# `session.start` / `screen.init` so the BED probe in
# casino.__main__ -> casino.cli and any direct `casino tictactoe`
# invocation gets the same terminal state as the sibling games.

import locale
import sys
import time

from bbsengine6 import io, screen, session
from bbsengine6.net.ping import PingUnavailable


def main(argv: list[str] | None = None) -> int:
    args = None

    session.start(args)

    screen.init()

    locale.setlocale(locale.LC_ALL, "")
    time.tzset()

    try:
        io.echo(
            "{level.error}tictactoe is BED-only in v1; no door-mode entry.{/all}"
        )
    except KeyboardInterrupt:
        io.echo("{/all}{bold}INTR{/bold}")
    except EOFError:
        io.echo("{/all}{bold}EOF{/bold}")
    except PingUnavailable as exc:
        io.echo(str(exc), level="error")
        return 1
    finally:
        io.echo(
            f"{{decsc}}{{curpos:{io.terminal.height()},0}}{{el}}{{decrc}}{{reset}}{{/all}}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
