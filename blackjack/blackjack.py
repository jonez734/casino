import argparse

import ttyio4 as ttyio
import bbsengine4 as bbsengine

def main():
    parser = argparse.ArgumentParser("blackjack")
    
    parser.add_argument("--verbose", action="store_true", dest="verbose")
    parser.add_argument("--debug", action="store_true", dest="debug")

    defaults = {"databasename": "zoidweb5", "databasehost":"localhost", "databaseuser": None, "databaseport":5433, "databasepassword":None}
    bbsengine.buildargdatabasegroup(parser, defaults)

    args = parser.parse_args()

if __name__ == "__main__":
    main()
