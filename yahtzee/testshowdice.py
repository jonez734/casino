import ttyio5 as ttyio
import bbsengine5 as bbsengine

def main():
    ttyio.echo("{f6:4}{cursorup:4}")
    selected = [0]
    round = 0
    while round < 13:
#        ttyio.echo("{clear}{home}")
        dice = bbsengine.diceroll(6, 5, mode="list")
        for x in range(0,5):
            value = dice[x]
            if x in selected:
                ttyio.echo("{green}", end="")
            else:
                ttyio.echo("{/all}", end="")
            ttyio.echo("{acs:ulcorner}{acs:hline:3}{acs:urcorner}{cursordown:1}{cursorleft:5}", end="")
            ttyio.echo("{acs:vline} %d {acs:vline}{cursorleft:5}{cursordown:1}" % (value), end="")
            ttyio.echo("{acs:llcorner}{acs:hline:3}{acs:lrcorner}{cursorright:2}{cursorup:2}", end="")
        break
        round += 1
    ttyio.echo("{f6:3}")
if __name__ == "__main__":
    main()
