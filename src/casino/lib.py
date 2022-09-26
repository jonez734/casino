import copy
import random

import ttyio5 as ttyio
import bbsengine5 as bbsengine

suits = {
    "H": "{u:heart}",
    "D": "{u:diamond}",
    "S": "{u:spade}",
    "C": "{u:club}"
}

class Card:
    def __init__(self, suit=None, pips=None, **attributes):
        self.pips = pips
        self.suit = suit
        self.attributes = attributes

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
    def __init__(self, args, location=None, bank=None):
      super().__init__("casino.casino")
      self.attributes = [
        { "name":"location", "type":"location", "default":location },
        { "name":"bank",     "type":"int",      "default": bank}
      ]
#      self.location = location
#      self.bank = bank
      self.dbh = bbsengine.databaseconnect(args)
      for a in self.attributes:
          setattr(self, a["name"], a["default"])

    def __edit(self, rec={}):
      origrec = copy.deepcopy(rec)
#      rec["id"] = ttyio.inputinteger("casinoid: ", self.id)
      rec["location"] = ttyio.inputstring("location: ", self.location)
      rec["bank"] = ttyio.inputinteger("bank: ", self.bank)
      return rec

    def add(self):
      origrec = {}
      rec = self.__edit(origrec)
    
    def load(self, casinoid):
      pass

# @since 20220815
def setarea(args, player, left):
  def right():
    currentmember = bbsengine.getcurrentmember(args)
    if currentmember is None:
      return ""
    rightbuf = "| %s | %s" % (currentmember["name"], bbsengine.pluralize(currentmember["credits"], "credit", "credits"))
    if args.debug is True:
      rightbuf += " | debug"
    return rightbuf
  bbsengine.setarea(left, right)

class Player(object):
  def __init__(self):
    self.memberid = None
    self.status = "active"
    self.lastvisit = "now()"
    self.tokens = 0
    self.stats = {}
  def incstat(self, game, stat):
    if game not in self.stats:
      self.stats[game] = {}
    
    if stat not in self.stats[game]:
      self.stats[game][stat] = 0
    self.stats[game][stat] += 1
    return
