from bbsengine6 import io, util, member


def init(args, **kw):
    return True


def access(args, op, **kw):
    return member.checkflag(args, "SYSOP", **kw)


def buildargs(args, **kw):
    return None


def main(args, **kw):
    sysop = member.checkflag(args, "SYSOP", **kw)
    if sysop is False:
        io.echo("permission denied.", level="error")
        return

    done = False
    while not done:
        util.heading("casino maint")
        io.echo("{optioncolor}[C]{labelcolor} Casino")
        io.echo("{optioncolor}[T]{labelcolor} Table")
        io.echo("{optioncolor}[G]{labelcolor} Game")
        io.echo("{optioncolor}[H]{labelcolor} Hand")
        io.echo("{optioncolor}[P]{labelcolor} Player")
        io.echo("{optioncolor}[X]{labelcolor} Exit")

        ch = io.inputchar(
            "{promptcolor}casino maint: {inputcolor}",
            "CTGHQX",
            "",
        )

        if ch == "X" or ch == "Q":
            done = True
        elif ch == "C":
            io.echo("Casino (not implemented)")
        elif ch == "T":
            io.echo("Table (not implemented)")
        elif ch == "G":
            io.echo("Game (not implemented)")
        elif ch == "H":
            io.echo("Hand (not implemented)")
        elif ch == "P":
            io.echo("Player (not implemented)")

    return True
