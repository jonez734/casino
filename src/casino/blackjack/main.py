from bbsengine6 import util, io, member
from .. import lib as libcasino
from . import lib

def init(args, **kw:dict) -> bool:
    return True

def access(args, op:str, **kw:dict) -> bool:
    return True

def buildargs(args, **kw:dict) -> bool:
    return None

def main(args, **kw):
    io.terminal.title("blackjack")
    shoe = libcasino.Shoe(decks=3)
    shoe.shuffle(3)

    player = lib.BlackjackPlayer()
    player.memberid = member.getcurrentid(args)
    io.echo(f"{player=}", level="debug")
    dealer = lib.BlackjackPlayer()
    dealer.kind = "dealer"

    done = False
    while not done:
        lib.runmodule(args, "play", player=player, dealer=dealer, **kw)
        # play(args, shoe, dealer.hand, player.hand)
        if io.inputboolean("{f6}{promptcolor}another hand? {optioncolor}[Yn]{promptcolor}: {inputcolor}", "Y") is False:
            break
            
    return True
