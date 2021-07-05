import argparse

import ttyio4 as ttyio
import bbsengine5 as bbsengine

import casino

def main():
    parser = argparse.ArgumentParser("blackjack")
    
    parser.add_argument("--verbose", action="store_true", dest="verbose")
    parser.add_argument("--debug", action="store_true", dest="debug")

    defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":5433, "databasepassword":None}
    bbsengine.buildargdatabasegroup(parser, defaults)

    args = parser.parse_args()

    bbsengine.title("blackjack")
    shoe = casino.initshoe(decks=3)
    casino.shuffleshoe(shoe)
#    ttyio.echo("after shuffle: shoe=%r" % (shoe))
    card = casino.drawcard(shoe)
#    ttyio.echo("after drawcard: shoe=%r" % (shoe))
    ttyio.echo("card=%r" % (card))
#    ttyio.echo("cards=%d decks=%d" % (len(shoe), len(shoe)/52))

if __name__ == "__main__":
    main()
