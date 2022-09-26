import ttyio5 as ttyio
import bbsengine5 as bbsengine

selected = {}
dice = []

def show(dice):
    for x in range(0,5):
        value = dice[x]
        if x in selected:
            ttyio.echo("{gray}", end="")
        else:
            ttyio.echo("{/all}", end="")
        ttyio.echo("{acs:ulcorner}{acs:hline:3}{acs:urcorner} {cursordown:1}{cursorleft:6}", end="")
        ttyio.echo("{acs:vline} %d {acs:vline} {cursorleft:6}{cursordown:1}" % (value), end="")
#        ttyio.echo("{acs:llcorner}{acs:hline:3}{acs:lrcorner}{cursorright:2}{cursorup:2}", end="")
        ttyio.echo("{acs:llcorner}{acs:hline:3}{acs:lrcorner} {cursordown:1}{cursorleft:6}", end="")
        ttyio.echo("{reverse}  %d  {/reverse}{cursorup:3}{cursorright:2}" % (x+1), end="")
    ttyio.echo("{/all}{f6:4}", end="")

def main():
    global selected
    global dice

    # roll three times. first time is all 5 dice, then 2 more rolls. after that, score.
    round = 0
    dice = bbsengine.diceroll(6, 5, mode="list")
    while round < 13:
        ttyio.echo("round: %d" % (round))
        done = False
        while not done:
            ttyio.echo("{f6:4}{cursorup:4}")
            show(dice)
            ch = ttyio.inputchar("re-roll [1-5,Q]: ", "12345Q", "")
            if ch == "Q":
                done = True
                ttyio.echo("End Round")
                break
#            ttyio.echo("selected=%r" % (selected), level="debug", interpret=False)
            h = ord(ch)-48-1 # 0 based
            if h in selected:
                del selected[h]
            else:
                selected[h] = True
        if ttyio.inputboolean("continue? [Yn]: ", "Y") is False:
            return
        for reroll in selected:
            dice[reroll] = bbsengine.diceroll(6, 1)
        selected = {}

        round += 1
    ttyio.echo("{f6:3}")

if __name__ == "__main__":
    try:
        main()
    except EOFError:
        ttyio.echo("{/all}{bold}EOF{/bold}")
    except KeyboardInterrupt:
        ttyio.echo("{/all}{bold}INTR{/bold}")
    finally:
        ttyio.echo("{/all}")
