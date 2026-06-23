from __future__ import annotations

import argparse
import random
from argparse import Namespace
from typing import Any

# import ttyio5 as ttyio
# import bbsengine5 as bbsengine
from bbsengine6 import io, database, screen, module, member, util

import tkinter as tk
from PIL import Image, ImageTk, ImageOps

PACKAGENAME = "casino"

suits = {"H": "{u:heart}", "D": "{u:diamond}", "S": "{u:spade}", "C": "{u:club}"}


class Card(object):
    def __init__(self, shorthand: str = "", facedown: bool = True, **kwargs: Any) -> None:
        self.shorthand = shorthand
        if shorthand is not None and shorthand != "":
            self.pips: str | None = self.shorthand[:-1] if len(self.shorthand) > 1 else None
            self.suit: str | None = self.shorthand[-1:] if len(self.shorthand) > 0 else None
            self.blank = False
        else:
            self.pips = None
            self.suit = None
            self.blank = True

        self.tkart = None
        self.show = True
        self.facedown = facedown
        self.art = None  # self.getart()

    def __repr__(self) -> str:
        return f"Card({self.shorthand=}, {self.suit=}, {self.pips=} {self.art=} {self.facedown=})"

    def value(self) -> int:
        if self.blank is True:
            return 0

        if self.pips == "A":
            v = 11
        elif self.pips in ("K", "Q", "J"):
            v = 10
        else:
            v = int(self.pips) if self.pips is not None else 0

        suit_char = suits.get(self.suit, "") if self.suit else ""
        io.echo(
            f"Card.value.120: card={self.pips}{suit_char} {v=}", level="debug"
        )
        return v

    def isace(self) -> bool:
        if self.pips == "A":
            return True
        return False


class tkCard(Card):
    def __init__(self, args: Any, **kwargs: Any) -> None:
        super().__init__(args, **kwargs)
        self.artpath = self.getartpath()

    def __repr__(self) -> str:
        return f"tkCard({self.shorthand=}, {self.artpath=}, {self.suit=}, {self.pips=} {self.getart()=} {self.facedown=})"

    def getartpath(self) -> str:
        suitname = "unknown"
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
            short = self.pips if self.pips is not None else "unknown"

        artpath = f"cards/{short}_of_{suitname}.png"
        return artpath

    def getart(self) -> ImageTk.PhotoImage:
        self.artpath = self.getartpath()
        with Image.open(self.artpath) as img:
            self.containedimage = ImageOps.contain(img, (100, 250))
            self.tkart = ImageTk.PhotoImage(self.containedimage)
        return self.tkart


class Hand(object):
    def __init__(self, label, **kwargs):
        self.id = None
        self.label = label
        #        self.shoe = shoe
        self.playerid = kwargs.get("playerid", None)
        #        self.cards = []
        self.value = 0
        self.index = 0
        self.cards = []
        self.status_override = None
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
        if self.status_override is not None:
            return self.status_override
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

    def hit(self, shoe):
        """Draw a card from shoe and add to hand."""
        card = shoe.draw()
        self.add(card)
        return card

    def stand(self):
        """Mark hand as standing."""
        self.standing = True

    def refresh(self):
        pass

    def totalpoints(self):
        points = 0
        for card in self.cards:
            points += card.value()
        return points


class tkHand(Hand):
    def __init__(self, text, **kwargs):
        super().__init__(text, **kwargs)

        #    self.tklabels = []
        #    self.images = []

        self.frame = kwargs["frame"] if "frame" in kwargs else None

        #    ttyio.echo(f"--> tkhand.init: self.frame={self.frame!r}", level="debug")

        self.row = kwargs["row"] if "row" in kwargs else 0
        self.paddings = kwargs["paddings"] if "paddings" in kwargs else {}

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
        # ttyio.echo(f"lib.tkHand.100: {card!r}", level="debug")
        #      art = card.getart()
        #      label = tk.Label(self.frame, bd=2, relief="solid", padx=20, pady=10)#, image=card.getart())
        #      label.configure(image=art)
        #      label.image = art
        #      label.grid(row=0, column=x)
        #      card.tklabel = label
        #      self.tklabels.append(label)
        self.refresh()

    #    ttyio.echo(f"---> tkHand.120: tklabels={self.tklabels!r}", level="debug")

    def show(self, hide: bool = True) -> None:
        for card in self.cards:
            io.echo(f"{self.label=}: {card=}", level="debug")

    def refresh(self) -> None:
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
            label = tk.Label(self.frame, bd=0, relief="solid", padx=50, pady=10)  # type: ignore[arg-type]
            label.configure(image=art)
            label.image = art  # type: ignore[union-attr]
            label.grid(row=0, column=x, padx=20)
            self.card_labels.append(label)
            points = card.value()
            totalpoints += points

            if points == 0:
                pointslabel = tk.Label(
                    self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10  # type: ignore[arg-type]
                )
            else:
                pointslabel = tk.Label(
                    self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10, text=points  # type: ignore[arg-type]
                )
            pointslabel.grid(row=1, column=x)
            self.points_labels.append(pointslabel)

        if totalpoints > 0:
            self.totalpoints_label = tk.Label(
                self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10, text=totalpoints  # type: ignore[arg-type]
            )
        else:
            self.totalpoints_label = tk.Label(
                self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10
            )

        self.totalpoints_label.grid(row=2, column=0, columnspan=5, sticky=tk.W + tk.E)


class Table:
    def __init__(
        self,
        shoeid: int | None = None,
        casinoid: int | None = None,
        minimumbet: int = 1,
        maximumbet: int = 10,
        bank: int = 0,
    ) -> None:
        self.id: int | None = None
        self.shoeid: int | None = shoeid
        self.casinoid: int | None = casinoid
        self.minimumbet = minimumbet
        self.maximumbet = maximumbet
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
    def __init__(self, args: Namespace | None = None, location: str | None = None, bank: int | None = None, ui: str = "tk") -> None:
        self.location: str | None = location
        self.bank: int | None = bank
        self.attributes = [
            {"name": "location", "type": "location", "default": location},
            {"name": "bank", "type": "int", "default": bank},
        ]
        self.dbh = database.connect(args) if args is not None else None
        for a in self.attributes:
            setattr(self, a["name"], a["default"])

    def __edit(self, rec: dict | None = None) -> dict:
        if rec is None:
            rec = {}
        rec["location"] = io.inputstring("{var:promptcolor}location: {var:inputcolor}", self.location if self.location else "")
        rec["bank"] = io.inputinteger("{var:promptcolor}bank: {var:inputcolor}", self.bank if self.bank else 0)
        return rec

    def add(self):
        self.__edit({})

    def load(self, casinoid):
        pass


class Seat:
    def __init__(self, memberid):
        self.memberid = memberid
        pass


_current_args = None
_current_player = None
_casino_fragments = []


def _casino_player_fragment(**kwargs) -> str:
    if _current_player is None:
        return ""
    return f"{_current_player.moniker}"


def _casino_credits_fragment(**kwargs) -> str:
    if _current_player is None:
        return ""
    return util.pluralize(_current_player.credits, "credit", "credits")


def _register_casino_fragments() -> None:
    for fn in (_casino_player_fragment, _casino_credits_fragment):
        if fn not in _casino_fragments:
            screen.register_bottombar_fragment(fn)
            _casino_fragments.append(fn)


def _unregister_casino_fragments() -> None:
    for fn in _casino_fragments:
        screen.unregister_bottombar_fragment(fn)
    _casino_fragments.clear()


def setbottombar(args, buf, **kwargs) -> None:
    global _current_args, _current_player
    _current_args = args
    _current_player = kwargs.get("player", _current_player)
    screen_kwargs = {}
    if args is not None:
        screen_kwargs["args"] = args
    pool = kwargs.get("pool", None)
    if pool is not None:
        screen_kwargs["pool"] = pool
    screen.setbottombar(buf, **screen_kwargs)
    _register_casino_fragments()
    return


# @since 20220815
def setarea(args: Namespace, left: str, player: Any = None) -> None:
    def right() -> str:
        currentmember = member.getcurrent(args)
        if currentmember is None:
            return ""
        rightbuf = f"| {currentmember['moniker']} | {util.pluralize(currentmember['credits'], 'credit', 'credits')}"
        if args.debug is True:
            rightbuf += " | debug"
        return rightbuf

    io.screen.setbottombar(left, right)


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


class CasinoPlayer:
    def __init__(self, args, membermoniker=None, pool=None):
        self.args = args
        self.pool = pool
        self.moniker = membermoniker
        self.credits = 1000
        self.stats = {}
        self._load()

    def _load(self):
        pass

    def save(self):
        pass


def buildargs(args: Namespace | None = None, **kwargs: Any) -> argparse.ArgumentParser:
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


def runmodule(args: Namespace | None, modulename: str, **kwargs: Any) -> Any:
##    io.echo(f"{args=} {modulename=}", level="debug")
    prefix = kwargs.get("prefix", "casino")
    return module.runmodule(args, f"{prefix}.{modulename}", **kwargs)
