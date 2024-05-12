PACKAGENAME = "casino.blackjack"

from bbsengine6 import module, database

from .. import lib as libcasino

class BlackjackPlayer(libcasino.Player):
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

def runmodule(args, modulename, **kw):
    return module.runmodule(args, f"{PACKAGENAME}.{modulename}", **kw)

def buildargs(args=None, **kw):
    parser = argparse.ArgumentParser("blackjack")
    parser.add_argument("--verbose", action="store_true", dest="verbose")
    parser.add_argument("--debug", action="store_true", dest="debug")

    defaults = {"databasename": "zoid6", "databasehost":"localhost", "databaseuser": None, "databaseport":5432, "databasepassword":None}
    database.buildargdatabasegroup(parser, defaults)

    return parser
