from bbsengine6 import util

def init(args, **kw):
    return True

def access(args, op, **kw):
    return True

def buildargs(args=None, **kw):
    return True

def main(args, **kw):
    util.heading("play blackjack")

    player.hand = libcasino.Hand("player 1")

    dealer.hand = libcasino.Hand("dealer")

    player.hand.add(shoe.draw())
    dealer.hand.add(shoe.draw())

    player.hand.add(shoe.draw())
    dealer.hand.add(shoe.draw())

