import random
import locale
import argparse

import ttyio4 as ttyio
import bbsengine5 as bbsengine

suits = {
    "H": "{u:heart}",
    "D": "{u:diamond}",
    "S": "{u:spade}",
    "C": "{u:club}"
}

class Card:
    def __init__(self, suit=None, pips=None):
        self.pips = pips
        self.suit = suit

    def value(self):
        if self.pips == "A":
            v = 11
        elif self.pips == "K":
            v = 10
        elif self.pips == "Q":
            v = 10
        elif self.pips == "J":
            v = 10
        else:
            v = int(self.pips)
        suit = self.suit if self.suit in suits else "??"

        ttyio.echo("Card.value.120: card=%s%s value=%r" % (self.pips, suits[self.suit], v), level="debug")
        return v

    def isace(self):
        if self.pips == "A":
            return True
        return False

class Table:
    def __init__(self, shoeid:int=None, casinoid:int=None, minimumbet:int=1, maximumbet:int=10, bank:int=0):
        self.id = None
        self.shoeid = shoeid
        self.casinoid = casinoid
        self.minimumbet = minimumbet
        self.maximumbet = maximumbet
        self.shoeid = shoeid
        self.bank = bank
    def update(self):
      pass
    def insert(self):
      attributes = { "casinoid": self.casinoid, "minimumbet": self.minimumbet, "maximumbet": self.maximumbet, "shoeid": self.shoeid, "bank": self.bank }
      pass
    def show(self):
      ttyio.echo("table: id=%r, casinoid=%r, shoeid=%r, minimumbet=%r, maximumbet=%r, bank=%r" % (self.id, self.casinoid, self.shoeid, self.minimumbet, self.maximumbet, self.bank), level="debug")
      return

class Shoe:
    def __init__(self, tableid=None, decks=3):
        self.id = None
        self.tableid = tableid
        self.cards = []
        if decks is None:
          return
        for d in range(0, decks):
            for suit in [ "S", "D", "C", "H" ]: # {u:spade}", "{u:diamond}", "{u:club}", "{u:heart}" ]:
                for pips in ["A", "K", "Q", "J", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]:
                    self.cards.append(Card(suit, pips))

    def shuffle(self, rounds=1):
        for x in range(0, rounds):
            ttyio.echo("Shoe.shuffle.100: running..", level="debug")
            random.shuffle(self.cards)
        return

    def show(self):
        if len(self.cards) == 0:
            ttyio.echo("this shoe is empty.")
            return
        for card in self.cards:
            ttyio.echo("%s%s " % (card.pips, card.suit), end="")
        ttyio.echo()
        return

    def remove(self, pips, suit):
        for c in self.cards:
            if c.pips == pips and c.suit == suit:
                del c
                return

    def draw(self):
        return self.cards.pop()

    def append(self, card:object=None):
      if card is None:
        return

      self.cards.append(card)
      return

def getcardtablelocations():
    cardtablelocations = [
      'Arnhem - Netherlands',
      'Barcelona - Spain',
      'Birmingham - England',
      'Budapest - Hungary',
      'Helsinki - Finland',
      'Munich - Germany',
      'Sicily - Italy',
      'Oslo - Norway',
      'Vienna - Austria',
      'Cape Town - South Africa'
    ]
    return cardtablelocations

class Casino(bbsengine.Node):
    def __init__(self, args, casinoid=None, location=None, bank=None):
      self.attributes = [
        { "name":"location", "type":"completelocation", "default":None },
        { "name":"bank", "type":"int", "default": 0}
      ]
      self.id = casinoid
      self.location = location
      self.bank = bank
      self.dbh = bbsengine.databaseconnect(args)
      for a in self.attributes:
          setattr(self, a["name"], a["default"])

      if casinoid is not None:
          ttyio.echo("Casino.__init__.100: calling load(%r)" % (casinoid), level="debug")
          self.load(casinoid)

    def __edit(self, rec={}):
      rec = {}
      rec["id"] = ttyio.inputinteger("casinoid: ", self.id)
      rec["location"] = ttyio.inputstring("location: ", self.location)
      rec["bank"] = ttyio.inputinteger("bank: ", self.bank)
      return rec

    def add(self):
      rec = self.__edit()
      c = Casino()
      c.location = rec["location"]
      c.bank = rec["bank"]
      c.id = rec["id"]

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

  menu = [
    { "label": "add",    "callback": add,     "description":""},# , "help": alphahelp},
    { "label": "edit",   "callback": edit,    "description":""},
    { "label": "list",   "callback": summary, "description":""},
    { "label": "delete", "callback": delete,  "description":""}
  ]

  done = False
  while not done:
    bbsengine.displaymenu(menu, "casino")
    res = bbsengine.handlemenu("casino: ", menu)
    if res is None:
      return
    elif type(res) == tuple:
      (op, i) = res
    else:
      ttyio.echo("invalid return type from handle menu %r!" % (type(res)), level="error")
      break

    if i < len(menu):
      if op == "select":
        ttyio.echo("{decrc}{var:menu.inputcolor}%s: %s{/all}" % (chr(ord('A')+i), menu[i]["label"]))
        bbsengine.runcallback(None, menu[i]["callback"], menuitem=menu[i])
        continue
      elif op == "help":
        m = menu[i]
        ttyio.echo("{decrc}display help for %s" % (m["label"]))
        if "help" in m:
          ttyio.echo(m["help"]+"{f6:2}")
        else:
          ttyio.echo("{f6}no help defined for this option{f6}")
        continue
    else:
      ttyio.echo("{decrc}Q: Quit{/all}")
      done = True
      break
  return

def table(args, **kwargs):
  pass

def maint(args):
  sysop = bbsengine.checkflag(args, "SYSOP")
  if sysop is False:
    ttyio.echo("permission denied.")
    # make a log entry for the security issue
    return

  menu = [
    { "label": "casino",  "callback": casino, "description":""},
    { "label": "table",   "callback": table, "description":""}
  ]

  done = False
  while not done:
    bbsengine.displaymenu(menu, "maint")
    try:
      res = bbsengine.handlemenu("casino maint: ", menu)
    except EOFError:
      ttyio.echo("{decrc}EOF")
      return
    if res is None:
      return
    elif type(res) == tuple:
      (op, i) = res
    else:
      ttyio.echo("invalid return type from handle menu %r!" % (type(res)), level="error")
      break

    if i < len(menu):
      if op == "select":
        ttyio.echo("{decrc}{var:menu.inputcolor}%s: %s{/all}" % (chr(ord('A')+i), menu[i]["label"]))
        bbsengine.runcallback(None, menu[i]["callback"], menuitem=menu[i])
        continue
      elif op == "help":
        m = menu[i]
        ttyio.echo("{decrc}display help for %s" % (m["label"]))
        if "help" in m:
          ttyio.echo(m["help"]+"{f6:2}")
        else:
          ttyio.echo("{f6}no help defined for this option{f6}")
        continue
    else:
      ttyio.echo("{decrc}Q: Quit{/all}")
      done = True
      break
  return

def main():
  parser = argparse.ArgumentParser("casino")

  parser.add_argument("--verbose", action="store_true", dest="verbose")

  parser.add_argument("--debug", action="store_true", dest="debug")

  defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":5432, "databasepassword":None}
  bbsengine.buildargdatabasegroup(parser, defaults)

  args = parser.parse_args()

  locale.setlocale(locale.LC_ALL, "")

  if args is not None and "debug" in args and args.debug is True:
      ttyio.echo("casino.main.100: args=%r" % (args))

  ttyio.setvariable("menu.boxcharcolor", "{bglightgray}{white}")
  ttyio.setvariable("menu.backgroundcolor", "{bggray}")
  ttyio.setvariable("menu.shadowbackgroundcolor", "{bgdarkgray}")
  ttyio.setvariable("menu.cursorcolor", "{bglightgray}{blue}")
  ttyio.setvariable("menu.boxcolor", "{bgblue}{green}")
  ttyio.setvariable("menu.itemcolor", "{blue}{bglightgray}")
  ttyio.setvariable("menu.titlecolor", "{black}{bglightgray}")
  ttyio.setvariable("menu.promptcolor", "{white}{bgblack}")
  ttyio.setvariable("menu.inputcolor", "{white}{bgblack}")

  maint(args)
  return

if __name__ == "__main__":
  try:
    main()
  except EOFError:
    ttyio.echo("{/all}{bold}EOF{/bold}")
  except KeyboardInterupt:
    ttyio.echo("{/all}{bold}INTR{/bold}")
  finally:
    ttyio.echo("{/all}")
