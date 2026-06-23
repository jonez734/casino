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
    with database.getpool(args, database=database.DEFAULTDATABASE) as pool:
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

    with database.getpool(args, database=args.databasename) as pool:
        with database.connect(args, pool=pool) as conn:
            # --- ensure bank schema exists (dependency) ---
            io.echo("schema {var:valuecolor}bank{var:labelcolor}: ", end="")
            if database.schemaexists(args, "bank", conn=conn) is False:
                io.echo("create ", end="")
                if database.createschema(args, "bank", conn=conn) is False:
                    io.echo("fail", level="error")
                    return False
            io.echo(" ok ", level="ok")

            # --- bank schema privs ---
            for r in ("web", "term", "sysop"):
                if (
                    database.manage_schema_priv(
                        args, "grant", "usage", "bank", r, conn=conn, **kwargs
                    )
                    is False
                ):
                    io.echo("fail", level="error")
                    return False
                else:
                    io.echo(" ok ", level="ok")

            failcount = 0

            # --- bank classes ---
            bank_classes = (
                ("bank.__account", "bank.sql"),
                ("bank.account", "bank.sql"),
                ("bank.__transaction", "bank.sql"),
                ("bank.transaction", "bank.sql"),
                ("bank.__transfer", "bank.sql"),
                ("bank.transfer", "bank.sql"),
            )
            for c, sql in bank_classes:
                io.echo(
                    f"{{var:labelcolor}}class {{var:valuecolor}}{c}{{var:labelcolor}}: ",
                    end="",
                )
                if database.classexists(args, c, conn=conn) is False:
                    io.echo("import ", end="")
                    if (
                        database.importsql(args, sql, conn=conn, package="bbsengine6.sql")
                        is False
                    ):
                        failcount += 1
                        io.echo("fail", level="error")
                    else:
                        io.echo(" ok ", level="ok")
                else:
                    io.echo("ok", level="ok")

            io.echo("schema {var:valuecolor}casino{var:labelcolor}: ", end="")
            if database.schemaexists(args, "casino", conn=conn) is False:
                io.echo("import ", end="")
                if database.importsql(args, "schema.sql", conn=conn, package="casino.sql") is False:
                    io.echo("fail", level="error")
                    return False
            io.echo(" ok ", level="ok")

            classlist: tuple[tuple[str, str], ...] = (
                ("casino.__player", "player.sql"),
                ("casino.player", "player_view.sql"),
                ("casino.__table", "table.sql"),
                ("casino.table", "table_view.sql"),
                ("casino.map_cardtable_player", "map_cardtable_player.sql"),
                ("casino.__game", "game.sql"),
                ("casino.map_game_player", "map_game_player.sql"),
                ("casino.game", "game_view.sql"),
                ("casino.__account", "account.sql"),
                ("casino.account", "account_view.sql"),
                ("casino.__betlog", "betlog.sql"),
                ("casino.betlog", "betlog_view.sql"),
                ("casino.__log", "log.sql"),
                ("casino.log", "log_view.sql"),
                ("casino.__hand", "hand.sql"),
                ("casino.hand", "hand_view.sql"),
            )

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

            if failcount == 0:
                io.echo(" ok ", level="ok")
            else:
                io.echo("fail", level="error")
                conn.rollback()

            return True if failcount == 0 else False
