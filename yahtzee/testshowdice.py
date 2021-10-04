import ttyio5 as ttyio
import bbsengine5 as bbsengine

def main():
    for x in bbsengine.diceroll(6, 5, mode="list"):
        ttyio.echo("x=%d" % (x))

if __name__ == "__main__":
    main()
