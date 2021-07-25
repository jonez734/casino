import argparse
import random

import ttyio4 as ttyio
import bbsengine5 as bbsengine

import casino

class Hand:
    def __init__(self, label="NEEDINFO"):
        self.playerid = None
        self.id = None
        self.cards = []
        self.value = 0
        self.label = label

    def adjustace(self):
        adjust = 0
        for card in self.cards:
            if card.isace() is False:
                continue
            if self.value > 21:
                adjust = 10
                ttyio.echo("set adjust to %s" % (adjust), level="debug")
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

    def append(self, card):
        self.cards.append(card)

    def show(self, hide=True):
        ttyio.echo("%s: " % (self.label), end="")
        counter = 0
        for c in self.cards:
            if len(self.cards) == 2 and counter == 1 and self.label == "dealer" and hide is True:
                ttyio.echo("{u:solidblock:2} ", end="")
            else:
                ttyio.echo("%s%s " % (c.pips, casino.suits[c.suit]), end="")
            counter += 1

        ttyio.echo(" [%d]" % (self.calcvalue()), level="debug")

def Player():
    def __init__(self, memberid=None, playerid=None):
        self.memberid = memberid
        self.id = playerid

def play(shoe, dealerhand, playerhand):
    choice = None

    done = False
    while not done:
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

        playervalue = playerhand.calcvalue()
        # playervalue = playerhand.adjustace()

        dealervalue = dealerhand.calcvalue()
        # dealervalue = dealerhand.adjustace()

        playerhand.show()
        dealerhand.show()

        if playervalue > 21:
            break

        # dealer
        dealervalue = dealerhand.calcvalue()
        # dealervalue = dealerhand.adjustace()

        if dealervalue > 21:
            break

        if playervalue == dealervalue:
            ttyio.echo("push. another round.")
            break
        if dealervalue == 17:
            ttyio.echo("dealer hits on soft 17", level="debug")
            dealerhand.append(shoe.draw(), hidden=True)
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

    playerhand.show(hide=False)
    dealerhand.show(hide=False)

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
    shoe = casino.Shoe(decks=3) # casino.initshoe(decks=3)
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
