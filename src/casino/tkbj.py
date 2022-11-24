import argparse
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageOps, ImageTk

import bbsengine5 as bbsengine
import ttyio5 as ttyio

import lib

class PlayerHand():
    def __init__(self):
        self.cards = []
    def append(self, card):
        if len(self.cards) < 6:
            self.cards.append(card)
            return True
        else:
            ttyio.echo("you have {}, and cannot add more to your hand. automagic win.".format(bbsengine.pluralize(len(self.cards), "card", "cards")))
            return False

class App(tk.Tk):
    def __init__(self, args):
        super().__init__()

        self.args = args
        self.sysop = False # bbsengine.checksysop(args)
        
        self.vars = {}

        self.title('Blackjack')
        # UI options
        paddings = {'padx': 10, 'pady': 10}

        # configure style
        self.style = ttk.Style(self)
        self.style.configure("TLabel",  font=("TkFixedFont", 11))
        self.style.configure("TButton", font=("TkFixedFont", 11)) #Helvetica", 11))
        self.style.configure("TEntry",  font=("TkFixedFont", 11))
        
        self.playerart = []
        self.dealerart = []

        # configure the grid
#        self.columnconfigure(0, weight=1)
#        self.columnconfigure(1, weight=3)

        self.configure(background="green")
        
        row = 0

        dealerframe = tk.LabelFrame(self, borderwidth=2, relief=tk.GROOVE, text="dealer")
        dealerframe.grid(column=0, row=row, columnspan=2, sticky=tk.W+tk.E, **paddings)
        
        row += 1
        
        playerframe = tk.LabelFrame(self, borderwidth=2, relief=tk.GROOVE, text="player")
        # playerframe.grid(column=0, row=row, columnspan=1, **paddings)
        playerframe.grid(column=0, row=row, **paddings)
        tk.Grid.rowconfigure(playerframe, row, weight=1)

        # update button
#        self.hitbutton = ttk.Button(self, text="hit", command=self.hit)
#        self.hitbutton.grid(column=1, row=row, sticky=tk.E, **paddings)

#        self.standbutton = ttk.Button(self, text="stand", command=self.stand)
#        self.standbutton.grid(column=2, row=row, sticky=tk.E, **paddings)

        self.bind('<Escape>', lambda e: self.quit())

#        shoe = lib.Shoe(decks=1)
#        shoe.shuffle(3)
#        shoe.show()
        
        self.cardarttable = lib.buildcardart()

        playerhand = []
        dealerhand = []
        
        column = 0
        
#        shoe = lib.Shoe()
        
#        playerhand.draw(lib.Shoe().draw())

        playerhand.append(lib.Card("2D"))
        dealerhand.append(lib.Card("KS"))
        playerhand.append(lib.Card("AH"))
        dealerhand.append(lib.Card("AS"))

        index = 0
        for card in playerhand:
            self.playerart.append(card.art)
            label = tk.Label(playerframe, image=self.playerart[index], **paddings)
            label.grid(column=index, row=0)
            index += 1
        
        index = 0
        for card in dealerhand:
            self.dealerart.append(card.art)
            label = tk.Label(dealerframe, image=self.dealerart[index], **paddings)
            label.grid(column=index, row=0)
            index += 1

    def hit(self):
        ttyio.echo("hit me!")
    def stand(self):
        ttyio.echo("stand")
    def loadcard(self, card):
        if self.cardarttable[card]["tk"] is not None:
            return self.cardarttable["tk"]

        img = Image.open(self.cardarttable[card]["artpath"]) # tk.Image.open("cards/2_of_diamonds.png")) # playerframe, file="cards/2_of_diamonds.png")
        containedimage = ImageOps.contain(img, (100, 200))

        self.cardarttable[card]["tk"] = ImageTk.PhotoImage(containedimage)
        return self.cardarttable[card]["tk"]

def buildargs(args=None, **kw):
    parser = argparse.ArgumentParser("tkbj")
    parser.add_argument("--verbose", action="store_true", dest="verbose")
    parser.add_argument("--debug", action="store_true", dest="debug")

#    defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":15433, "databasepassword":None} # port=5432
    defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":5432, "databasepassword":None} # port=5432
    bbsengine.buildargdatabasegroup(parser)

    return parser

if __name__ == "__main__":
    parser = buildargs()
    args = parser.parse_args()

    app = App(args)
    app.mainloop()
