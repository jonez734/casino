# casino/yahtzee/__main__.py
# Yahtzee subpackage entry point.
#
# Mirrors casino/blackjack/__main__.py. Boots the BBS session, sets
# up the terminal, then dispatches to yahtzee/game.py via
# bbsengine6.module.run.

import locale
import time

from bbsengine6 import io, module, screen, session

args = None

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
finally:
    io.echo(
        f"{{decsc}}{{curpos:{io.getterminalheight()},0}}{{el}}{{decrc}}{{reset}}{{/all}}"
    )
