from bbsengine6 import io, util


selected = {}
dice = []


def show(dice):
    for x in range(0, 5):
        value = dice[x]
        if x in selected:
            io.echo("{gray}", end="")
        else:
            io.echo("{/all}", end="")
        io.echo(
            "{acs:ulcorner}{acs:hline:3}{acs:urcorner} {cursordown:1}{cursorleft:6}",
            end="",
        )
        io.echo(
            "{acs:vline} %d {acs:vline} {cursorleft:6}{cursordown:1}" % (value), end=""
        )
        io.echo(
            "{acs:llcorner}{acs:hline:3}{acs:lrcorner} {cursordown:1}{cursorleft:6}",
            end="",
        )
        io.echo(
            "{reverse}  %d  {/reverse}{cursorup:3}{cursorright:2}" % (x + 1), end=""
        )
    io.echo("{/all}{f6:4}", end="")


def init(args, **kw):
    return True


def access(args, op, **kw):
    return True


def buildargs(args=None, **kw):
    return None


def main(args=None, **kw):
    global selected
    global dice

    round = 0
    dice = util.diceroll(6, 5, mode="list")
    while round < 13:
        io.echo("round: %d" % (round))
        done = False
        while not done:
            io.echo("{f6:4}{cursorup:4}")
            show(dice)
            ch = io.inputchar("re-roll [1-5,Q]: ", "12345Q", "")
            if ch == "Q":
                done = True
                io.echo("End Round")
                break
            h = ord(ch) - 48 - 1
            if h in selected:
                del selected[h]
            else:
                selected[h] = True
        if io.inputboolean("continue? [Yn]: ", "Y") is False:
            return
        for reroll in selected:
            dice[reroll] = util.diceroll(6, 1)
        selected = {}

        round += 1
    io.echo("{f6:3}")
    return True
