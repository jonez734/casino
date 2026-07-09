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
    with database.getpool(args) as pool:
        with database.connect(args, pool=pool) as conn:
            io.echo("schema {var:valuecolor}casino{var:labelcolor}: ", end="")
            if database.schemaexists(args, "casino", conn=conn) is False:
                io.echo("import ", end="")
                if database.importsql(args, "schema.sql", conn=conn, package="casino.sql") is False:
                    io.echo("fail", level="error")
                    return False
            io.echo(" ok ", level="ok")

            failcount = 0

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
                ("casino.__hand", "hand.sql"),
                ("casino.hand", "hand_view.sql"),
                ("casino.__betlog", "betlog.sql"),
                ("casino.betlog", "betlog_view.sql"),
                ("casino.__log", "log.sql"),
                ("casino.log", "log_view.sql"),
                ("casino.__slot_spin", "slots.sql"),
                ("casino.slot_spin", "slot_spin_view.sql"),
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


