from bbsengine6 import util, io
from .. import lib as libcasino


def init(args, **kw):
    return True


def access(args, op, **kw):
    return True


def buildargs(args=None, **kw):
    return None


def main(args, **kw):
    player = kw["player"] if "player" in kw else None
    dealer = kw["dealer"] if "dealer" in kw else None
    shoe = kw["shoe"] if "shoe" in kw else None

    util.heading("play blackjack")

    player.hand = libcasino.Hand("player 1")

    dealer.hand = libcasino.Hand("dealer")

    player.hand.add(shoe.draw())
    dealer.hand.add(shoe.draw())

    player.hand.add(shoe.draw())
    dealer.hand.add(shoe.draw())

    io.echo(f"{player.hand=}")
    io.echo(f"{dealer.hand=}")
