import time
import locale

from bbsengine6 import io, screen, session
from . import lib

parser = lib.buildargs()
args = parser.parse_args() if parser is not None else None

session.start(args)

screen.init()

locale.setlocale(locale.LC_ALL, "")
time.tzset()

# module.init(args)

try:
    lib.runmodule(args, "main")
except KeyboardInterrupt:
    io.echo("{/all}{bold}INTR{bold}")
except EOFError:
    io.echo("{/all}{bold}EOF{/bold}")
finally:
    io.echo("{decsc}{curpos:%d,0}{el}{decrc}{reset}{/all}" % (io.getterminalheight()))
