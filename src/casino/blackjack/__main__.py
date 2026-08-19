import locale
import sys
import time

from bbsengine6 import io, module, screen, session
from bbsengine6.net.ping import PingUnavailable

from . import lib

parser = lib.buildargs()
args = parser.parse_args() if parser is not None else None

session.start(args)

screen.init()

locale.setlocale(locale.LC_ALL, "")
time.tzset()

# module.init(args)

try:
    module.run(args, "game", package="casino.blackjack")
except KeyboardInterrupt:
    io.echo("{/all}{bold}INTR{/bold}")
except EOFError:
    io.echo("{/all}{bold}EOF{/bold}")
except PingUnavailable as exc:
    io.echo(str(exc), level="error")
    sys.exit(1)
finally:
    io.echo(f"{{decsc}}{{curpos:{io.getterminalheight()},0}}{{el}}{{decrc}}{{reset}}{{/all}}")
