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

class Casino:
    def __init__(self, casinoid=None, location=None):
        self.id = casinoid
        self.location = location
    def __edit(self):
      pass

def maint(args):
  sysop = bbsengine.checkflag(args, "SYSOP")
  if sysop is False:
    ttyio.echo("permission denied.")
    return
  ttyio.echo("maint mode!")
  bbsengine.title("casino maint mode")
  ttyio.echo("[C]asino")
  ttyio.echo("[T]able")
  ttyio.echo("{f6}[Q]uit")
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

  maint(args)
  return

if __name__ == "__main__":
  main()
