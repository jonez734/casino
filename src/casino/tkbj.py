import argparse

import tkinter as tk
import tkinter.font as tkf
from tkinter import ttk

from PIL import Image, ImageOps, ImageTk

#import bbsengine5 as bbsengine
#import ttyio5 as ttyio
from bbsengine6 import io, member, database

import lib

class PlayerHand(lib.tkHand):
    def __init__(self, label, **kw):
        super().__init__(label, **kw)

        self.frame = kw["frame"] if "frame" in kw else None
        io.echo(f"playerhand.init.100: self.frame={self.frame!r}", level="debug")

        self.label = label

    def __repr__(self):
        return f"PlayerHand(label={self.label!r} cards={self.cards!r} frame={self.frame!r})"

class DealerHand(lib.tkHand):
    def __init__(self, label, **kw):
        super().__init__(label, **kw)

        self.frame = kw["frame"] if "frame" in kw else None
        io.echo(f"dealerhand.init.100: self.frame={self.frame!r}", level="debug")

        self.label = label

    def __repr__(self):
        return f"DealerHand(label={self.label!r} cards={self.cards!r} frame={self.frame!r})"

class App(tk.Tk):
    def __init__(self, args):
        super().__init__()

        self.args = args

        playermoniker = member.getcurrentmoniker(args)
        if playermoniker is None:
            io.echo("You do not exist! Go away!", level="error")
            return False

        self.sysop = False # bbsengine.checksysop(args)
        
        self.vars = {}

        self.title("Blackjack")

        # UI options
        self.paddings = {'padx': 10, 'pady': 10}

        self.labelfont = tkf.Font(family="Helvetica", size=24, weight="bold")

        # configure style
        self.style = ttk.Style(self)
        self.style.configure("TLabel",  font=self.labelfont) # ("Helvetica", 16))
        self.style.configure("TButton", font=("Helvetica", 12)) #Helvetica", 11))
        self.style.configure("TEntry",  font=("Helvetica", 16))
        self.style.configure("TLabelFrame",  font=self.labelfont) # ("Helvetica", 20))

        self.configure(background="#009000")

        self.shoe = lib.Shoe()
        self.shoe.shuffle()
#        self.shoe.show()

        self.row = 0

        self.playerframe = tk.LabelFrame(self, borderwidth=4, relief=tk.GROOVE, text=f"player: {playermoniker}")
        self.playerframe.grid(column=0, row=self.row, **self.paddings)
        self.playerframe.configure(font=self.labelfont)

        self.playerhand = PlayerHand(f"Player: {playermoniker}", row=self.row, frame=self.playerframe)
        io.echo(f"--> self.playerhand={self.playerhand!r}", level="debug")
        
        self.row += 1

        self.dealerframe = tk.LabelFrame(self, borderwidth=4, relief=tk.GROOVE, text=f"dealer")

        self.dealerhand = DealerHand("Dealer", row=self.row, frame=self.dealerframe)

        self.dealerframe.grid(column=0, row=self.row, **self.paddings)
        self.dealerframe.configure(font=self.labelfont)

        self.row += 1

        self.actions()

        self.bind('<Escape>', lambda e: self.quit())

        column = 0
        
        self.shoe = lib.Shoe()
        self.shoe.shuffle()
        self.shoe.show()
        
         # no one can possibly know the first card dealt. makes card counting more difficult
        self.shoe.draw()

        self.playerhand.add(self.shoe.draw(), facedown=False) # lib.Card("4S"))
        self.dealerhand.add(self.shoe.draw(), facedown=False) # lib.Card("4S"))
        self.playerhand.add(self.shoe.draw(), facedown=False) # lib.Card("4S"))
        self.dealerhand.add(self.shoe.draw(), facedown=True) # lib.Card("4S"))

    def actions(self):
        self.actionframe = tk.LabelFrame(self, borderwidth=2, text="player actions")
        self.actionframe.grid(column=0, row=self.row, columnspan=5, sticky=tk.W+tk.E, **self.paddings)
        self.actionframe.configure(font=self.labelfont)
        
        self.hitbutton = tk.Button(self.actionframe, text="hit", command=self.hit)
        self.hitbutton.pack(side=tk.TOP, fill=tk.BOTH) # grid(column=0, row=row, sticky=tk.NSEW)
        self.hitbutton.configure(font=self.labelfont)
        
        self.standbutton = tk.Button(self.actionframe, text="stand", command=self.stand)
        self.standbutton.pack(side=tk.TOP, fill=tk.BOTH) # grid(column=1, row=row, sticky=tk.NSEW)
        self.standbutton.configure(font=self.labelfont)
        
    def stand(self):
        io.echo("stand")
        self.hitbutton.configure(state=tk.DISABLED)
        self.dealerhand.cards[1].facedown = False
        self.dealerhand.refresh()
        return

    def hit(self):
        # count non-blank cards, and if the total is 5, automatic win
        nonblankcount = 0
        totalpoints = 0
        for card in self.playerhand.cards:
            if card.blank is False:
                nonblankcount += 1
                totalpoints += card.value()

        if totalpoints >= 21:
            io.echo("player loss: bust")
            self.playerhand.status = "bust"
            return

        if nonblankcount == 5:
            io.echo("player wins: 5 cards without a bust")
            self.playerhand.status = "win"
            return
            
        io.echo("hit me!")
        card = self.shoe.draw()
        self.playerhand.add(card)
        return "OK"

def buildargs(args=None, **kw):
    parser = argparse.ArgumentParser("tkbj")
    parser.add_argument("--verbose", action="store_true", dest="verbose")
    parser.add_argument("--debug", action="store_true", dest="debug")

#    defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":15433, "databasepassword":None} # port=5432
    defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":5432, "databasepassword":None} # port=5432
    database.buildarggroup(parser)

    return parser

if __name__ == "__main__":
    parser = buildargs()
    args = parser.parse_args()

    app = App(args)
    app.mainloop()
