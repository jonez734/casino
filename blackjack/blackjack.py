import argparse
import random

import ttyio4 as ttyio
import bbsengine5 as bbsengine

import casino

player = None
dealer = None

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

class Player(object):
    def __init__(self, memberid=None, playerid=None):
        self.memberid = memberid
        self.id = playerid
        self.currentbet = 0
        self.hand = None

    def sethand(self, hand=None):
        self.hand = hand

def play(shoe, dealerhand, playerhand):
    global player, dealer

    choice = None

    dealer.sethand(dealerhand)
    player.sethand(playerhand)

    done = False
    while not done:
        player.hand.show()
        dealer.hand.show()

        playerstatus = player.hand.status()
        ttyio.echo("player status: %s" % (playerstatus))
        if playerstatus == "win" or playerstatus == "naturalblackjack" or playerstatus == "blackjack":
            ttyio.echo("player wins: %s" % (playerstatus))
            ttyio.echo("dealer loss")
            break
        if playerstatus == "bust":
            ttyio.echo("player bust")
            ttyio.echo("dealer win")
            break

        dealerstatus = dealer.hand.status()
        ttyio.echo("dealer status: %s" % (dealerstatus))
        if dealerstatus == "win" or dealerstatus == "naturalblackjack" or dealerstatus == "blackjack":
            ttyio.echo("dealer wins: %s" % (dealerstatus))
            ttyio.echo("player loss")
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
                player.hand.append(shoe.draw())
                ttyio.echo("hit")
                choice = "hit"

        playervalue = player.hand.calcvalue()
        # playervalue = playerhand.adjustace()

        dealervalue = dealer.hand.calcvalue()
        # dealervalue = dealerhand.adjustace()

        player.hand.show()
        dealer.hand.show()

        if playervalue > 21:
            break

        # dealer
        dealervalue = dealer.hand.calcvalue()
        # dealervalue = dealerhand.adjustace()

        if dealervalue > 21:
            break

        if playervalue == dealervalue:
            ttyio.echo("push. another round.")
            break
        if dealervalue == 17:
            ttyio.echo("dealer hits on soft 17", level="debug")
            dealer.hand.append(shoe.draw(), hidden=True)
        elif dealervalue < 17:
            ttyio.echo("dealer < 17, hit", level="debug")
            dealer.hand.append(shoe.draw())

        dealervalue = dealer.hand.calcvalue()

        if dealervalue > 21:
            break
        elif dealervalue >= 18:
            break

        if playervalue < 21:
            continue

    ttyio.echo("end hand")
    dealerhandvalue = dealer.hand.calcvalue()
    playerhandvalue = player.hand.calcvalue()
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
    elif dealerhandvalue == 21:
        if len(dealer.hand) == 2:
            dealerstatus = "naturalblackjack"
            playerstatus = "loss"
        else:
            dealerstatus = "blackjack"
            playerstatus = "loss"
    elif playerhandvalue == 21:
        if len(player.hand) == 2:
            playerstatus = "naturalblackjack"
            dealerstatus = "loss"
        else:
            playerstatus = "blackjack"
            dealerstatus = "loss"

    player.hand.show(hide=False)
    dealer.hand.show(hide=False)

    if dealerstatus in ("win", "naturalblackjack", "blackjack"):
        ttyio.echo("dealer: %s, player: %s" % (dealerstatus, playerstatus))
    elif playerstatus in ("win", "naturalblackjack", "blackjack"):
        ttyio.echo("player: %s, dealer: %s" % (playerstatus, dealerstatus))
    else:
        ttyio.echo("push")

def main():
    global player, dealer

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

    player = Player()
    ttyio.echo("player=%r" % (player), level="debug")
    dealer = Player()

    done = False
    while not done:
        playerhand = Hand("player")
        player.sethand(playerhand)

        dealerhand = Hand("dealer")
        dealer.sethand(dealerhand)

        player.hand.append(shoe.draw())
        dealer.hand.append(shoe.draw())

        playerhand.append(shoe.draw())
        dealer.hand.append(shoe.draw())

        play(shoe, dealerhand, playerhand)
        if ttyio.inputboolean("another hand? [Yn]: ", "Y") is False:
            break

if __name__ == "__main__":
    main()
