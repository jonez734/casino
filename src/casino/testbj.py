import argparse

import tkinter as tk
import tkinter.font as tkf
import tkinter.ttk as ttk

from bbsengine6 import io, database, member

import lib


class PlayerHand(lib.tkHand):
    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)

        self.frame = kwargs["frame"] if "frame" in kwargs else None
        io.echo(f"playerhand.init.100: self.frame={self.frame!r}", level="debug")

        self.label = label

    def __repr__(self):
        return f"PlayerHand(label={self.label!r} cards={self.cards!r} frame={self.frame!r})"


class DealerHand(lib.tkHand):
    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)

        self.frame = kwargs["frame"] if "frame" in kwargs else None
        io.echo(f"dealerhand.init.100: self.frame={self.frame!r}", level="debug")

        self.label = label

    def __repr__(self):
        return f"DealerHand(label={self.label!r} cards={self.cards!r} frame={self.frame!r})"


class App(tk.Tk):
    def __init__(self, args):
        super().__init__()

        self.args = args

        currentmember = member.getcurrent(self.args)
        if currentmember is None:
            io.echo("You do not exist! Go away!", level="error")
            return

        playername = currentmember.get("moniker")

        self.sysop = False  # bbsengine.checksysop(args)

        self.vars = {}

        self.title("Blackjack")

        # UI options
        self.paddings = {"padx": 10, "pady": 10}

        self.labelfont = tkf.Font(family="Helvetica", size=24, weight="bold")

        # configure style
        self.style = ttk.Style(self)
        self.style.configure("TLabel", font=self.labelfont)  # ("Helvetica", 16))
        self.style.configure("TButton", font=("Helvetica", 12))  # Helvetica", 11))
        self.style.configure("TEntry", font=("Helvetica", 16))
        self.style.configure("TLabelFrame", font=self.labelfont)  # ("Helvetica", 20))

        self.configure(background="#009000")

        self.shoe = lib.Shoe()
        self.shoe.shuffle()
        #        self.shoe.show()

        self.row = 0

        self.playerframe = tk.LabelFrame(
            self, borderwidth=4, relief=tk.GROOVE, text=f"player: {playername}"
        )
        self.playerframe.grid(column=0, row=self.row, padx=10, pady=10)
        self.playerframe.configure(font=self.labelfont)

        self.playerhand = PlayerHand(
            f"Player: {playername}", row=self.row, frame=self.playerframe
        )
        io.echo(f"--> self.playerhand={self.playerhand!r}", level="debug")

        self.row += 1

        self.dealerframe = tk.LabelFrame(
            self, borderwidth=4, relief=tk.GROOVE, text="dealer"
        )

        self.dealerhand = DealerHand("Dealer", row=self.row, frame=self.dealerframe)

        self.dealerframe.grid(column=0, row=self.row, padx=10, pady=10)
        self.dealerframe.configure(font=self.labelfont)

        self.row += 1

        self.actions()

        self.bind("<Escape>", lambda e: self.quit())

        self.shoe = lib.Shoe()
        self.shoe.shuffle()
        self.shoe.show()

        # no one can possibly know the first card dealt. makes card counting more difficult
        self.shoe.draw()

        self.playerhand.add(self.shoe.draw(), facedown=False)  # lib.Card("4S"))
        self.dealerhand.add(self.shoe.draw(), facedown=False)  # lib.Card("4S"))
        self.playerhand.add(self.shoe.draw(), facedown=False)  # lib.Card("4S"))
        self.dealerhand.add(self.shoe.draw(), facedown=True)  # lib.Card("4S"))

    #        self.playerhand.show()
    #        for card in self.playerhand.cards:
    #            print(f"card={card!r}")
    #
    def actions(self):
        self.actionframe = tk.LabelFrame(self, borderwidth=2, text="player actions")
        self.actionframe.grid(
            column=0, row=self.row, columnspan=5, sticky=tk.W + tk.E, padx=10, pady=10
        )
        self.actionframe.configure(font=self.labelfont)

        self.hitbutton = tk.Button(self.actionframe, text="hit", command=self.hit)
        self.hitbutton.pack(
            side=tk.TOP, fill=tk.BOTH
        )  # grid(column=0, row=row, sticky=tk.NSEW)
        self.hitbutton.configure(font=self.labelfont)

        self.standbutton = tk.Button(self.actionframe, text="stand", command=self.stand)
        self.standbutton.pack(
            side=tk.TOP, fill=tk.BOTH
        )  # grid(column=1, row=row, sticky=tk.NSEW)
        self.standbutton.configure(font=self.labelfont)

    def stand(self):
        io.echo("stand")
        self.hitbutton.configure(state=tk.DISABLED)
        self.dealerhand.cards[1].facedown = False
        self.dealerhand.refresh()

        return

    def hit(self):
        #        if len(self.cards) == 5:
        #            io.echo("Automagic win, 5 cards without a bust!")
        #            return "WIN"

        #        if self.check() == "OK"

        io.echo("hit me!")
        card = self.shoe.draw()
        # card.tklabel = tk.Label(self.playerframe, image=self.playerart[index], **self.paddings)
        # card.tklabel.pack(side=tk.LEFT) # grid(column=index, row=0)

        self.playerhand.add(card)
        #        for i in range(0, 5):
        #            self.image = self.cards[i].getart()
        #            self.tklabels[i].configure(image=self.image)
        #            self.tklabels[i].pack()
        #            self.images.append(self.image)
        return "OK"


def buildargs(args=None, **kwargs):
    parser = argparse.ArgumentParser("tkbj")
    parser.add_argument("--verbose", action="store_true", dest="verbose")
    parser.add_argument("--debug", action="store_true", dest="debug")

    defaults = {
        "databasename": "zoid6",
        "databasehost": "localhost",
        "databaseuser": None,
        "databaseport": 5432,
        "databasepassword": None,
    }
    database.buildargs(parser, defaults)

    return parser


if __name__ == "__main__":
    parser = buildargs()
    args = parser.parse_args()

    app = App(args)
    app.mainloop()
