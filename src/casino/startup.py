from bbsengine6 import io, database


def init(args, **kwargs):
    io.register_emojis(
        {
            "slot": "\U0001f3b0",  # 🎰
            "card": "\U0001f0cf",  # 🃏
            "dice": "\U0001f3b2",  # 🎲
            "spade": "\U00002660",  # ♠
            "heart": "\U00002665",  # ♥
            "diamond": "\U00002666",  # ♦
            "club": "\U00002663",  # ♣
            "chip": "\U0001f0b2",  # 🂲
            "money": "\U0001f4b0",  # 💰
        }
    )
    return True


def access(args, op, **kwargs):
    return True


def buildargs(args, **kwargs):
    return None


def main(args, **kwargs):
    with database.getpool(args, dbname=database.DEFAULTDATABASE) as pool:
        with database.connect(args, pool=pool) as conn:
            io.echo(
                f"database {{var:valuecolor}}{args.databasename}{{var:labelcolor}}: ",
                end="",
                flush=True,
            )
            if database.exists(args, args.databasename, pool=pool) is False:
                io.echo(
                    "{var:valuecolor}fail{var:labelcolor}",
                    level="error",
                    flush=True,
                )
                return False
            else:
                io.echo(" ok ", level="ok", flush=True)

    with database.getpool(args, dbname=args.databasename) as pool:
        with database.connect(args, pool=pool) as conn:
            io.echo("schema {var:valuecolor}casino{var:labelcolor}: ", end="")
            if database.schemaexists(args, "casino", conn=conn) is False:
                io.echo("create ", end="")
                if database.createschema(args, "casino", conn=conn) is False:
                    io.echo("fail", level="error")
                    return False
            io.echo(" ok ", level="ok")
            io.echo(
                "{var:labelcolor}schema {var:valuecolor}casino{var:labelcolor} priv: ",
                end="",
            )
            if (
                database.manage_schema_priv(
                    args, "grant", "usage", "casino", "term", conn=conn
                )
                is False
            ):
                io.echo("fail", level="error")
                return False
            else:
                io.echo(" ok ", level="ok")

            classlist: tuple[tuple[str, str], ...] = (
                ("casino.table", "table.sql"),
                ("casino.hand", "hand.sql"),
            )

            failcount = 0
            for c, sql in classlist:
                io.echo(
                    f"{{var:labelcolor}}class {{var:valuecolor}}{c}{{var:labelcolor}}: ",
                    end="",
                )
                if database.classexists(args, c, conn=conn) is False:
                    io.echo("import ", end="")
                    if (
                        database.importsql(args, sql, conn=conn, package="casino.sql")
                        is False
                    ):
                        failcount += 1
                    else:
                        io.echo(" ok ", level="ok")
                else:
                    io.echo("ok", level="ok")

            io.echo(
                "{var:labelcolor}schema {var:valuecolor}casino {var:labelcolor}privs: ",
                end="",
            )
            for r in ("web", "term", "sysop"):
                if (
                    database.manage_schema_priv(
                        args, "grant", "usage", "casino", r, conn=conn, **kwargs
                    )
                    is False
                ):
                    io.echo("fail", level="error")
                    failcount += 1
                else:
                    io.echo(" ok ", level="ok")

            io.echo(
                "{var:labelcolor}schema {var:valuecolor}casino {var:labelcolor}create priv for sysop: ",
                end="",
            )
            if (
                database.manage_schema_priv(
                    args, "grant", "create", "casino", "sysop", conn=conn, **kwargs
                )
                is False
            ):
                io.echo("fail", level="error")
                failcount += 1
            else:
                io.echo(" ok ", level="ok")

            if failcount == 0:
                io.echo(" ok ", level="ok")
            else:
                io.echo("fail", level="error")
                conn.rollback()

            return True if failcount == 0 else False
