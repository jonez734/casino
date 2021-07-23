import argparse
import random

import ttyio4 as ttyio
import bbsengine5 as bbsengine

import casino

class Casino:
    def __init__(self, casinoid=None, location=None):
        self.id = casinoid
        self.location = location

class Table:
    def __init__(self, casinoid=None, minimumbet=1, maximumbet=10):
        self.id = None
        self.shoeid = None
        self.casinoid = casinoid
        self.minimumbet = minimumbet
        self.maximumbet = maximumbet
        return

class Shoe:
    def __init__(self, tableid=None, decks=3):
        self.id = None
        self.tableid = tableid
        self.cards = []
        for d in range(0, decks):
            for suit in [ "{u:spade}", "{u:diamond}", "{u:club}", "{u:heart}" ]:
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
        for c in self.cards:
            ttyio.echo("%s%s " % (c.pips, c.suit), end="")
        ttyio.echo()
        return

    def remove(self, pips, suit):
        for c in self.cards:
            if c.pips == pips and c.suit == suit:
                del c
                return

    def draw(self):
        return self.cards.pop()

class Card:
    def __init__(self, suit=None, pips=None):
        self.pips = pips
        self.suit = suit

    def value(self):
        if self.pips == "A":
            v = 14
        elif self.pips == "K":
            v = 10
        elif self.pips == "Q":
            v = 10
        elif self.pips == "J":
            v = 10
        else:
            v = int(self.pips)
        # ttyio.echo("Card.value.120: card=%s%s value=%r" % (self.pips, self.suit, v), level="debug")
        return v

class Hand:
    def __init__(self, label="NEEDINFO"):
        self.playerid = None
        self.id = None
        self.cards = []
        self.value = 0
        self.label = label

    def calcvalue(self):
        v = 0
        for c in self.cards:
            v += c.value()
        self.value = v
        return self.value

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

    def adjustace(self, mode="player"):
        if mode == "player":
            ch = ttyio.inputchar("ace. [A] 11 or [B] 1", "AB", "")
            if ch == "A":
                return 11
            elif ch == "B":
                return 1
        elif mode == "dealer":
            # check for ace, use "1" if "11" would bust.
            pass
    def append(self, card):
        self.cards.append(card)

    def show(self):
        ttyio.echo("%s: " % (self.label), end="")
        for c in self.cards:
            ttyio.echo("%s%s " % (c.pips, c.suit), end="")
        ttyio.echo(" [%d]" % (self.calcvalue()))

def play(shoe, dealerhand, playerhand):
    choice = None

    done = False
    while not done:
#        ttyio.echo("playerhand=%r" % (playerhand), level="debug")
#        ttyio.echo("dealerhand=%r" % (dealerhand), level="debug")

        playerhand.show()
        dealerhand.show()

        playerstatus = playerhand.status()
        ttyio.echo("player status: %s" % (playerstatus))
        if playerstatus == "win" or playerstatus == "naturalblackjack" or playerstatus == "blackjack":
            ttyio.echo("player wins")
            ttyio.echo("dealer lose")
            break
        if playerstatus == "bust":
            ttyio.echo("player bust")
            ttyio.echo("dealer win")
            break

        dealerstatus = dealerhand.status()
        ttyio.echo("dealer status: %s" % (dealerstatus))
        if dealerstatus == "win" or dealerstatus == "naturalblackjack" or dealerstatus == "blackjack":
            ttyio.echo("dealer wins")
            ttyio.echo("player lose")
            break
        if dealerstatus == "bust":
            ttyio.echo("dealer bust")
            ttyio.echo("player win")
            break
        if choice != "stand":
            ch = ttyio.inputchar("player [H]it or [S]tand: ", "HS", "")
            if ch == "S":
                ttyio.echo("stand")
                choice = "stand"
            elif ch == "H":
                playerhand.append(shoe.draw())
                ttyio.echo("hit")
                choice = "hit"

        playerhand.show()
        dealerhand.show()
        playervalue = playerhand.calcvalue()
        if playervalue > 21:
            break
        # dealer
        dealervalue = dealerhand.calcvalue()
        if playervalue == dealervalue:
            ttyio.echo("push. another round.")
            break
        if dealervalue == 17:
            ttyio.echo("dealer hits on soft 17", level="debug")
            dealerhand.append(shoe.draw())
        elif dealervalue < 17:
            ttyio.echo("dealer < 17, hit", level="debug")
            dealerhand.append(shoe.draw())

        dealervalue = dealerhand.calcvalue()

        if dealervalue > 21:
            break
        elif dealervalue >= 18:
            break

        if playervalue < 21:
            continue

    ttyio.echo("end hand")
    dealerhandvalue = dealerhand.calcvalue()
    playerhandvalue = playerhand.calcvalue()
    if dealerhandvalue > 21:
        playerstatus = "win"
        dealerstatus = "bust"
    elif playerhandvalue > 21:
        playerstatus = "bust"
        dealerstatus = "win"
    elif playerhandvalue == dealerhandvalue:
        playerstatus = "push"
        dealerstatus = "push"
    elif dealerhandvalue > playerhandvalue:
        dealerstatus = "win"
        playerstatus = "loss"
    elif playerhandvalue > dealerhandvalue:
        playerstatus = "win"
        dealerstatus = "loss"
    playerhand.show()
    dealerhand.show()
    if dealerstatus in ("win", "naturalblackjack", "blackjack"):
        ttyio.echo("dealer: %s, player: %s" % (dealerstatus, playerstatus))
    elif playerstatus in ("win", "naturalblackjack", "blackjack"):
        ttyio.echo("player: %s, dealer: %s" % (playerstatus, dealerstatus))
    else:
        ttyio.echo("push")

def main():
    parser = argparse.ArgumentParser("blackjack")
    
    parser.add_argument("--verbose", action="store_true", dest="verbose")
    parser.add_argument("--debug", action="store_true", dest="debug")

    defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":5433, "databasepassword":None}
    bbsengine.buildargdatabasegroup(parser, defaults)

    args = parser.parse_args()

    bbsengine.title("blackjack")
    shoe = Shoe(decks=3) # casino.initshoe(decks=3)
#    shoe.show()
    shoe.shuffle(3) # casino.shuffleshoe(shoe)
#    ttyio.echo("------")
#    shoe.show()
#    ttyio.echo("shuffled shoe=%r" % (shoe))

    done = False
    while not done:
        playerhand = Hand("player")
        dealerhand = Hand("dealer")

        playerhand.append(shoe.draw())
        dealerhand.append(shoe.draw())

        playerhand.append(shoe.draw())
        dealerhand.append(shoe.draw())

        play(shoe, dealerhand, playerhand)
        if ttyio.inputboolean("another hand? [Yn]: ", "Y") is False:
            break

if __name__ == "__main__":
    main()
