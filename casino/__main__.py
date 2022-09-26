import random
import locale
import argparse

import ttyio5 as ttyio
import bbsengine5 as bbsengine

import libcasino


if __name__ == "__main__":
  locale.setlocale(locale.LC_ALL, "")

  parser = buildargs()
  args = parser.parse_args()

  ttyio.echo("{f6:3}{cursorup:3}", end="") # curpos:%d,0}" % (ttyio.getterminalheight()-3))
  bbsengine.initscreen(bottommargin=1)

  try:
      main(args)
  except KeyboardInterrupt:
      ttyio.echo("{/all}{bold}INTR{bold}")
  except EOFError:
      ttyio.echo("{/all}{bold}EOF{/bold}")
  finally:
      ttyio.echo("{decsc}{curpos:%d,0}{el}{decrc}{reset}{/all}" % (ttyio.getterminalheight()))
