import random
import locale
import argparse

import ttyio5 as ttyio
import bbsengine5 as bbsengine

def casino(args):
  def add(args, **kwargs):
    return

  done = False
  while not done:
    bbsengine.title("casino")
    ttyio.echo("[A]dd")
    ttyio.echo("[L]ist")
    ttyio.echo("[E]dit")
    ttyio.echo("{f6}[Q]uit{f6}")
    ch = ttyio.inputchar("casino [ALEQ]: ", "ALEQ", "Q")
    if ch == "Q":
      ttyio.echo("Quit")
      done = True
    elif ch == "A":
      ttyio.echo("Add")
      add()
    elif ch == "L":
      ttyio.echo("List")
      summary()
    elif ch == "E":
      ttyio.echo("Edit")
      edit()

def casino(args, **kwargs):
  def add(args, **kwargs):
    bbsengine.title("add casino")
    ttyio.echo("casino.add.120: args=%r" % (args), interpret=False)
    c = Casino(args)
    c.add()
    ttyio.echo("casino.add.100: %r" % (c), level="debug", interpret=False)

  def edit(args, **kwargs):
    pass

  def summary(args, **kwargs):
    pass
  
  def delete(args, **kwargs):
    pass

  menuitems = [
    { "name": "add",    "label": "add",    "callback": add,     },# , "help": alphahelp},
    { "name": "edit",   "label": "edit",   "callback": edit,    },
    { "name": "list",   "label": "list",   "callback": summary, },
    { "name": "delete", "label": "delete", "callback": delete,  }
  ]

  menu = bbsengine.Menu("casino maint", menuitems, args=args)
  menu.run("casino: ")
  return

def table(args, **kwargs):
  pass

def maint(args, **kwargs):
  sysop = bbsengine.checkflag(args, "SYSOP")
  if sysop is False:
    ttyio.echo("permission denied.")
    # make a log entry for the security issue
    return

  menuitems = [
    { "name":"casino", "label": "casino",  "callback": casino},
    { "name":"table",  "label": "table",   "callback": table},
    { "name":"game",   "label": "game",    "callback": "game"},
    { "name":"hand",   "label": "hand",    "callback": "hand"},
    { "name":"player", "label": "player",  "callback": "player"},
  ]

  menu = bbsengine.Menu("casino maint", menuitems, args=args)
  menu.run("maint: ")
#    bbsengine.poparea()
  return

def buildargs():
  parser = argparse.ArgumentParser("casino")

  parser.add_argument("--verbose", action="store_true", dest="verbose")

  parser.add_argument("--debug", action="store_true", dest="debug")

  defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":5432, "databasepassword":None}
  bbsengine.buildargdatabasegroup(parser, defaults)
  return parser

def main(args):

  args = parser.parse_args()

  locale.setlocale(locale.LC_ALL, "")

  if args is not None and "debug" in args and args.debug is True:
      ttyio.echo("casino.main.100: args=%r" % (args))

  ttyio.setvariable("engine.menu.boxcharcolor", "{bglightgray}{darkgreen}")
  ttyio.setvariable("engine.menu.color", "{bggray}")
  ttyio.setvariable("engine.menu.shadowcolor", "{bgdarkgray}")
  ttyio.setvariable("engine.menu.cursorcolor", "{bglightgray}{blue}")
  ttyio.setvariable("engine.menu.boxcolor", "{bgblue}{green}")
  ttyio.setvariable("engine.menu.itemcolor", "{blue}{bglightgray}")
  ttyio.setvariable("engine.menu.titlecolor", "{black}{bglightgray}")
  ttyio.setvariable("engine.menu.promptcolor", "{lightgray}")
  ttyio.setvariable("engine.menu.inputcolor", "{white}")
  ttyio.setvariable("engine.menu.disableditemcolor", "{darkgray}")
  ttyio.setvariable("engine.menu.resultfailedcolor", "{bgred}{white}")
  ttyio.setvariable("engine.currentoptioncolor", "{bggray}{white}")
  ttyio.setvariable("engine.areacolor", "{bggray}{white}")
  
  dbh = bbsengine.databaseconnect(args)

  menuitems = []
  if bbsengine.getflag(dbh, "SYSOP") is True:
    menuitems.append({ "name": "maint",     "label": "maint",     "callback": maint})
  menuitems.append({ "name": "blackjack", "label": "blackjack", "callback": "blackjack"})
  menuitems.append({ "name": "yahtzee",   "label": "yahtzee",   "callback": "yahtzee"})
  menuitems.append({ "name": "poker",     "label": "poker",     "callback": "poker"})
  menu = bbsengine.Menu("casino", menuitems, args=args)
  menu.run("casino: ")

#  maint(args)
  return

if __name__ == "__main__":
  parser = buildargs()
  args = parser.parse_args()

  try:
    main(args)
  except EOFError:
    ttyio.echo("{/all}{bold}EOF{/bold}")
  except KeyboardInterrupt:
    ttyio.echo("{/all}{bold}INTR{/bold}")
  finally:
    ttyio.echo("{/all}")
