import time
import random
import locale
import argparse

import ttyio5 as ttyio
import bbsengine5 as bbsengine

from . import lib

player = None
dealer = None

class BlackjackPlayer(lib.Player):
    def __init__(self):
        super().__init__()
        self.playerid = None
        self.currentbet = 0
        self.hand = None
        self.stats["blackjack"] = {}
        for s in ("win", "loss", "draw", "bust", "blackjack", "naturalblackjack"):
            self.stats["blackjack"][s] = 0
    def incstat(self, stat):
        return super().incstat("blackjack", stat)

def play(args, shoe, dealerhand, playerhand):
    global player, dealer

    choice = None

    dealer.hand = dealerhand
    player.hand = playerhand

    done = False
    while not done:
        lib.setarea(args, player, "blackjack")
        
        bbsengine.title("start hand")

        player.hand.show()
        dealer.hand.show()

        playerstatus = player.hand.status()
        ttyio.echo("player status: %s" % (playerstatus))
        if playerstatus == "win" or playerstatus == "naturalblackjack" or playerstatus == "blackjack":
            ttyio.echo("player wins: %s" % (playerstatus))
            ttyio.echo("dealer loss")
#            player.incstat("win")
#            dealer.incstat("loss")
            break
        if playerstatus == "bust":
            ttyio.echo("player bust")
            ttyio.echo("dealer win")
#            player.incstat("bust")
#            dealer.incstat("win")
            break

        dealerstatus = dealer.hand.status()
        ttyio.echo("dealer status: %s" % (dealerstatus))
        if dealerstatus == "win" or dealerstatus == "naturalblackjack" or dealerstatus == "blackjack":
            ttyio.echo("dealer wins: %s" % (dealerstatus))
            ttyio.echo("player loss")
#            player.incstat("loss")
#            dealer.incstat("win")
            break
        if dealerstatus == "bust":
            ttyio.echo("dealer bust")
            ttyio.echo("player win")
 #           player.incstat("win")
 #           dealer.incstat("bust")
            break

        if choice != "stand":
            ch = ttyio.inputchar("{var:promptcolor}player {var:optioncolor}[H]{var:promptcolor}it, {var:optioncolor}[S]{var:promptcolor}tand, or {var:optioncolor}[Q]{var:promptcolor}uit: {var:inputcolor}", "HSQ", "")
            if ch == "S":
                ttyio.echo("stand")
                choice = "stand"
            elif ch == "H":
                player.hand.append(shoe.draw())
                ttyio.echo("hit")
                choice = "hit"
            elif ch == "Q":
                ttyio.echo("Quit")
                break

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

    bbsengine.title("end hand")
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
    
    player.incstat(playerstatus)
    dealer.incstat(dealerstatus)

    ttyio.echo("player.stats=%r" % (player.stats), level="debug")
    ttyio.echo("dealer.stats=%r" % (dealer.stats), level="debug")

def buildargs(args=None, **kw):
    parser = argparse.ArgumentParser("blackjack")

    parser.add_argument("--verbose", action="store_true", dest="verbose")
    parser.add_argument("--debug", action="store_true", dest="debug")

    defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":5432, "databasepassword":None}
    bbsengine.buildargdatabasegroup(parser, defaults)

    return parser

def init(args, **kw):
    return True

def main(args, **kw):
    global player, dealer

    bbsengine.title("blackjack")
    shoe = lib.Shoe(decks=3)
    shoe.shuffle(3)

    player = BlackjackPlayer()
    player.memberid = bbsengine.getcurrentmemberid(args)
    ttyio.echo("player=%r" % (player), level="debug")
    dealer = BlackjackPlayer()
    dealer.type = "dealer"

    done = False
    while not done:
        player.hand = lib.Hand("player 1")

        dealer.hand = lib.Hand("dealer")

        player.hand.add(shoe.draw())
        dealer.hand.add(shoe.draw())

        player.hand.add(shoe.draw())
        dealer.hand.add(shoe.draw())

        play(args, shoe, dealer.hand, player.hand)
        if ttyio.inputboolean("{var:promptcolor}another hand? [{var:optioncolor}Yn{var:promptcolor}]: {var:inputcolor}", "Y") is False:
            break
            
    return True

if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, "")
    time.tzset()

    parser = buildargs()
    args = parser.parse_args()

    ttyio.echo("{f6:3}{cursorup:3}") # curpos:%d,0}" % (ttyio.getterminalheight()-3))
    bbsengine.initscreen()

    init(args)

    try:
        main(args)
    except KeyboardInterrupt:
        ttyio.echo("{/all}{bold}INTR{bold}")
    except EOFError:
        ttyio.echo("{/all}{bold}EOF{/bold}")
    finally:
        ttyio.echo("{decsc}{curpos:%d,0}{eraseline}{decrc}{reset}{/all}" % (ttyio.getterminalheight()))
