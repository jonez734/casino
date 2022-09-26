def casino(args, **kwargs):
  def add(args, **kwargs):
    bbsengine.title("add casino")
    ttyio.echo("casino.add.120: args=%r" % (args), interpret=False)
    c = libcasino.Casino(args)
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

  menu = bbsengine.Menu("maint casino", menuitems, args=args)
  menu.run("maint casino: ")
  return

def table(args, **kwargs):
  pass

def maint(args, **kwargs):
  sysop = bbsengine.checksysop(args)
  if sysop is False:
    ttyio.echo("permission denied.")
    # make a log entry for the security issue
    return

  menuitems = [
    { "name":"casino", "label": "casino",  "callback": "casino"},
    { "name":"table",  "label": "table",   "callback": "table"},
    { "name":"game",   "label": "game",    "callback": "game"},
    { "name":"hand",   "label": "hand",    "callback": "hand"},
    { "name":"player", "label": "player",  "callback": "player"},
  ]

  menu = bbsengine.Menu("maint", menuitems, args=args)
  menu.run("maint: ")
#    bbsengine.poparea()
  return

def buildargs(args=None, **kw):
  parser = argparse.ArgumentParser("casino")

  parser.add_argument("--verbose", action="store_true", dest="verbose")

  parser.add_argument("--debug", action="store_true", dest="debug")

  defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":5432, "databasepassword":None}
  bbsengine.buildargdatabasegroup(parser, defaults)
  return parser

def main(args, **kw):

  if args is not None and "debug" in args and args.debug is True:
      ttyio.echo("casino.main.100: args=%r" % (args), level="debug")

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
  if bbsengine.checksysop(args) is True:
    menuitems.append({ "name": "maint",     "label": "maint",     "callback": "maint"})
  menuitems.append({ "name": "blackjack", "label": "blackjack", "callback": "blackjack"})
  menuitems.append({ "name": "yahtzee",   "label": "yahtzee",   "callback": "yahtzee"})
  menuitems.append({ "name": "poker",     "label": "poker",     "callback": "poker"})


  print(bbsengine.runsubmodule(args, "casino.blackjack"))
#  menu = bbsengine.Menu("casino", menuitems, args=args)
#  menu.run("casino: ")

#  maint(args)
  return
