"""Tk card, hand and table classes for the casino Tk UI.

These extend the UI-neutral Card, Hand and Table classes in casino.lib. casino.lib does not import
this module. Card images come from the playingcarddata package (see casino.tk.card_images).
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from bbsengine6 import io

from casino.lib import Card, Hand, Table
from casino.tk import card_images

class tkCard(Card):
    def __init__(self, args: Any, **kwargs: Any) -> None:
        super().__init__(args, **kwargs)
        self.artpath = self.getartpath()

    def __repr__(self) -> str:
        return f"tkCard({self.shorthand=}, {self.artpath=}, {self.suit=}, {self.pips=} {self.getart()=} {self.facedown=})"

    def getartpath(self) -> str:
        """The image's file name in the playingcarddata set (the card back and blank are named)."""
        if self.suit is None and self.pips is None:
            return card_images.CARD_BLANK
        if self.facedown is True:
            return card_images.CARD_BACK
        suit = card_images.SUIT_FROM_LETTER.get(self.suit or "", "")
        return card_images.card_filename(self.pips or "", suit)

    def getart(self) -> Any:
        # PIL is imported here, not at module level: the package imports lib.py, so a wheel build
        # or any import of casino must not need Pillow. Only the Tk UI calls getart().
        from PIL import Image, ImageOps, ImageTk

        self.artpath = self.getartpath()
        path = card_images.image_path(self.artpath)
        with Image.open(path) as img:
            self.containedimage = ImageOps.contain(img, (100, 250))
            self.tkart = ImageTk.PhotoImage(self.containedimage)
        return self.tkart


class tkHand(Hand):
    def __init__(self, text, **kwargs):
        super().__init__(text, **kwargs)

        #    self.tklabels = []
        #    self.images = []

        self.frame = kwargs.get("frame")

        #    ttyio.echo(f"--> tkhand.init: self.frame={self.frame!r}", level="debug")

        self.row = kwargs.get("row", 0)
        self.paddings = kwargs.get("paddings", {})

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


class tkTable(Table):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
