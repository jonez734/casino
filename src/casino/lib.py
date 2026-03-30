import argparse
import random

# import ttyio5 as ttyio
# import bbsengine5 as bbsengine
from bbsengine6 import io, database, screen, module, member, util

import tkinter as tk
from PIL import Image, ImageTk, ImageOps

PACKAGENAME = "casino"

suits = {"H": "{u:heart}", "D": "{u:diamond}", "S": "{u:spade}", "C": "{u:club}"}


class Card(object):
    def __init__(self, shorthand: str = "", facedown=True, **kw):
        self.shorthand = shorthand
        if shorthand is not None and shorthand != "":
            self.pips, self.suit = self.shorthand[:-1], self.shorthand[-1:]
            self.blank = False
        else:
            self.pips, self.suit = None, None
            self.blank = True

        self.tkart = None
        self.show = True
        self.facedown = facedown
        self.art = None  # self.getart()

    def __repr__(self):
        return f"Card({self.shorthand=}, {self.suit=}, {self.pips=} {self.art=} {self.facedown=})"

    def value(self):
        if self.blank is True:
            return 0

        if self.pips == "A":
            v = 11
        elif self.pips in ("K", "Q", "J"):
            v = 10
        else:
            v = int(self.pips)

        io.echo(
            f"Card.value.120: card={self.pips}{suits[self.suit]} {v=}", level="debug"
        )
        return v

    def isace(self):
        if self.pips == "A":
            return True
        return False


class tkCard(Card):
    def __init__(self, args, **kw):
        super().__init__(args, **kw)
        self.artpath = self.getartpath()

    def __repr__(self):
        return f"tkCard({self.shorthand=}, {self.artpath=}, {self.suit=}, {self.pips=} {self.getart()=} {self.facedown=})"

    def getartpath(self):
        if self.suit is None and self.pips is None:
            artpath = "cards/card-blank-008000.png"
        elif self.facedown is True:
            artpath = "cards/card-back-electricblue.png"
        elif self.suit == "D":
            suitname = "diamonds"
        elif self.suit == "H":
            suitname = "hearts"
        elif self.suit == "S":
            suitname = "spades"
        elif self.suit == "C":
            suitname = "clubs"

        if self.pips == "A":
            short = "ace"
        elif self.pips == "J":
            short = "jack"
        elif self.pips == "Q":
            short = "queen"
        elif self.pips == "K":
            short = "king"
        else:
            short = self.pips

        artpath = f"cards/{short}_of_{suitname}.png"
        return artpath

    def getart(self):
        self.artpath = self.getartpath()
        with Image.open(self.artpath) as img:
            self.containedimage = ImageOps.contain(img, (100, 250))
            self.tkart = ImageTk.PhotoImage(self.containedimage)
        return self.tkart

    def add(self, card, facedown=False):
        card.getart()
        super().add(card, facedown)


class Hand(object):
    def __init__(self, label, **kw):
        self.id = None
        self.label = label
        #        self.shoe = shoe
        self.playerid = kw.get("playerid", None)
        #        self.cards = []
        self.value = 0
        self.index = 0
        self.cards = []
        for i in range(0, 5):
            self.cards.append(Card(facedown=False))
        io.echo("hand initialized, blank cards added")

    def adjustace(self):
        adjust = 0
        for card in self.cards:
            if card.isace() is False:
                continue
            if self.value > 21:
                adjust = 10
                io.echo(f"set adjust to {adjust}", level="debug")
                break
        return adjust

    def calcvalue(self):
        self.value = 0
        for c in self.cards:
            self.value += c.value()

        adjust = 0
        if self.value > 21:
            adjust = self.adjustace()
        return self.value - adjust

    def status(self):
        value = self.calcvalue()
        if value > 21:
            return "bust"
        if value == 21:
            if len(self.cards) == 2:
                return "naturalblackjack"
            else:
                return "blackjack"
        return "play"

    def add(self, card, facedown=False):
        card.facedown = facedown
        #        ttyio.echo(f"--> len(self.cards)={len(self.cards)}, self.index={self.index}")
        self.cards[self.index] = card
        self.index += 1
        self.refresh()

    def show(self, hide=True):
        io.echo(f"{self.label}: ", end="")
        counter = 0
        for c in self.cards:
            if (
                len(self.cards) == 2
                and counter == 1
                and self.label == "dealer"
                and hide is True
            ):
                io.echo("{u:solidblock:2} ", end="")
            else:
                io.echo(f"{c.pips}{suits[c.suit]} ", end="")
            counter += 1

        io.echo(f" [{self.calcvalue()}]", level="debug")

    def hit(self):
        pass

    def stand(self):
        pass

    def refresh(self):
        pass

    def totalpoints(self):
        points = 0
        for card in self.cards:
            points += card.value()
        return points


class tkHand(Hand):
    def __init__(self, text, **kw):
        super().__init__(text, **kw)

        #    self.tklabels = []
        #    self.images = []

        self.frame = kw["frame"] if "frame" in kw else None

        #    ttyio.echo(f"--> tkhand.init: self.frame={self.frame!r}", level="debug")

        self.row = kw["row"] if "row" in kw else 0
        self.paddings = kw["paddings"] if "paddings" in kw else {}

        self.card_labels = []
        self.points_labels = []
        self.totalpoints_label = None

        #    ttyio.echo(f"--> self.frame={self.frame!r}", level="debug")

        #    self.playerframe = tk.LabelFrame(self, borderwidth=4, relief=tk.GROOVE, text=f"player: {playername}")
        #    self.playerframe.grid(column=0, row=row, **self.paddings)
        #    self.playerframe.configure(font=labelfont)

        #    for x in range(0, 5):
        #      card = self.cards[x]
        ##      card = Card(shortname="4S", blank=False, facedown=False)
        #      ttyio.echo(f"lib.tkHand.100: {card!r}", level="debug")
        #      art = card.getart()
        #      label = tk.Label(self.frame, bd=2, relief="solid", padx=20, pady=10)#, image=card.getart())
        #      label.configure(image=art)
        #      label.image = art
        #      label.grid(row=0, column=x)
        #      card.tklabel = label
        #      self.tklabels.append(label)
        self.refresh()

    #    ttyio.echo(f"---> tkHand.120: tklabels={self.tklabels!r}", level="debug")

    def show(self):
        for card in self.cards:
            io.echo(f"{self.label=}: {card=}", level="debug")

    def refresh(self):
        for label in self.card_labels:
            label.destroy()
        for label in self.points_labels:
            label.destroy()
        if self.totalpoints_label is not None:
            self.totalpoints_label.destroy()

        self.card_labels = []
        self.points_labels = []

        totalpoints = 0
        for x in range(0, 5):
            points = 0
            card = self.cards[x]
            art = card.getart()
            label = tk.Label(self.frame, bd=0, relief="solid", padx=50, pady=10)
            label.configure(image=art)
            label.image = art
            label.grid(row=0, column=x, padx=20)
            self.card_labels.append(label)
            points = card.value()
            totalpoints += points

            if points == 0:
                pointslabel = tk.Label(
                    self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10
                )
            else:
                pointslabel = tk.Label(
                    self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10, text=points
                )
            pointslabel.grid(row=1, column=x)
            self.points_labels.append(pointslabel)

        if totalpoints > 0:
            self.totalpoints_label = tk.Label(
                self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10, text=totalpoints
            )
        else:
            self.totalpoints_label = tk.Label(
                self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10
            )

        self.totalpoints_label.grid(row=2, column=0, columnspan=5, sticky=tk.W + tk.E)


class Table:
    def __init__(
        self,
        shoeid: int = None,
        casinoid: int = None,
        minimumbet: int = 1,
        maximumbet: int = 10,
        bank: int = 0,
    ):
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
        pass

    def show(self):
        io.echo(
            f"table: {self.id=}, {self.casinoid=}, {self.shoeid=}, {self.minimumbet=}, {self.maximumbet=}, {self.bank=}",
            level="debug",
        )
        return


class tkTable(Table):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent


class Shoe:
    def __init__(self, tableid=None, decks=1):
        self.id = None
        self.tableid = tableid
        self.cards = []

        if decks is None:
            return

        for d in range(0, decks):
            for suit in [
                "S",
                "D",
                "C",
                "H",
            ]:  # {u:spade}", "{u:diamond}", "{u:club}", "{u:heart}" ]:
                for pips in [
                    "A",
                    "K",
                    "Q",
                    "J",
                    "2",
                    "3",
                    "4",
                    "5",
                    "6",
                    "7",
                    "8",
                    "9",
                    "10",
                ]:
                    self.cards.append(
                        Card(shorthand=f"{pips}{suit}", facedown=False, blank=False)
                    )

    def shuffle(self, rounds=1):
        for x in range(0, rounds):
            io.echo("Shoe.shuffle.100: running..", level="debug")
            random.shuffle(self.cards)
        return

    def show(self):
        if len(self.cards) == 0:
            io.echo("this shoe is empty.")
            return
        for card in self.cards:
            io.echo(f"{card.pips}{card.suit} ", end="")
        io.echo()
        return

    def remove(self, pips, suit):
        for c in self.cards:
            if c.pips == pips and c.suit == suit:
                del c
                return

    def draw(self):
        card = self.cards.pop()
        io.echo(f"shoe.draw.100: {card=}", level="debug")
        return card

    def append(self, card: object = None):
        if card is None:
            return

        self.cards.append(card)
        return


def getcardtablelocations():
    cardtablelocations = [
        "Arnhem - Netherlands",
        "Barcelona - Spain",
        "Birmingham - England",
        "Budapest - Hungary",
        "Helsinki - Finland",
        "Munich - Germany",
        "Sicily - Italy",
        "Oslo - Norway",
        "Vienna - Austria",
        "Cape Town - South Africa",
    ]
    return cardtablelocations


class Casino(object):
    def __init__(self, args, location=None, bank=None, ui="tk"):
        super().__init__("casino.casino")
        self.attributes = [
            {"name": "location", "type": "location", "default": location},
            {"name": "bank", "type": "int", "default": bank},
        ]
        #      self.location = location
        #      self.bank = bank
        self.dbh = database.connect(args)
        for a in self.attributes:
            setattr(self, a["name"], a["default"])

    def __edit(self, rec=None):
        if rec is None:
            rec = {}
        #      rec["id"] = ttyio.inputinteger("casinoid: ", self.id)
        rec["location"] = io.inputstring("location: ", self.location)
        rec["bank"] = io.inputinteger("bank: ", self.bank)  # as in an amount of credits
        return rec

    def add(self):
        self.__edit({})

    def load(self, casinoid):
        pass


class Seat:
    def __init__(self, memberid):
        self.memberid = memberid
        pass


# @since 20220815
def setarea(args, left, player=None):
    def right():
        currentmember = member.getcurrent(args)
        if currentmember is None:
            return ""
        rightbuf = f"| {currentmember['moniker']} | {util.pluralize(currentmember['credits'], 'credit', 'credits')}"
        if args.debug is True:
            rightbuf += " | debug"
        return rightbuf

    screen.setarea(left, right)


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


def buildargs(args=None, **kw):
    parser = argparse.ArgumentParser("skel")
    parser.add_argument("--verbose", action="store_true", dest="verbose")
    parser.add_argument("--debug", action="store_true", dest="debug")

    defaults = {
        "databasename": "zoid6",
        "databasehost": "localhost",
        "databaseuser": None,
        "databaseport": 5432,
        "databasepassword": None,
    }
    database.buildarggroup(parser, defaults)

    return parser


def runmodule(args, modulename, **kw):
    io.echo(f"{args=} {modulename=}", level="debug")
    return module.runmodule(args, f"casino.{modulename}", **kw)
