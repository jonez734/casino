import argparse

import tkinter as tk
import tkinter.font as tkf
from tkinter import ttk

from bbsengine6 import io, database, member


class App(tk.Tk):
    def __init__(self, args):
        super().__init__()

        self.args = args

        currentmember = member.getcurrent(self.args)
        if currentmember is None:
            io.echo("You do not exist! Go away!", level="error")
            return

        self.sysop = False  # member.checkflag(args, "sysop")

        self.bind("<Escape>", lambda e: self.quit())
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

        self.row = 0
        self.tkfields = []
        self.fields = {
            "casinoid": {
                "type": "combobox",
                "default": None,
                "label": "casino",
                "value": None,
                "fk": "casino.id",
            },
            "name": {"type": "entry", "default": None, "label": "name", "value": None},
            "bank": {"type": "entry", "default": None, "label": "bank", "value": None},
            "minimumbet": {
                "type": "entry",
                "default": 5,
                "label": "minimum bet",
                "value": None,
            },
            "maximumbet": {
                "type": "entry",
                "default": 25,
                "label": "maximum bet",
                "value": None,
            },
            "location": {
                "type": "entry",
                "default": None,
                "label": "location",
                "value": None,
            },
        }

        for n, v in self.fields.items():
            self.tkfields.append(tk.Label(self, text=n))


def init(args, **kw):
    return True


def access(args, **kw):
    return True


def buildargs(args=None, **kw):
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
