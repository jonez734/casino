from bbsengine6 import database, io

from . import checkcasino


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
    with database.getpool(args) as pool, database.connect(args, pool=pool) as conn:

        # 1. Extensions — citext is required by casino.__player.membermoniker
        #    and by the new __bank_player.membermoniker.  Fresh-DB bootstrap
        #    crashes on the first table creation without this.
        io.echo("extension {var:valuecolor}citext{var:labelcolor}: ", end="")
        if database.extensionavailable(args, "citext", conn=conn) is False:
            io.echo("not in pg_available_extensions", level="error")
            return False
        if database.extensioninstalled(args, "citext", conn=conn) is False:
            io.echo("install ", end="")
            if database.creatextension(args, "citext", conn=conn) is False:
                io.echo("fail", level="error")
                return False
        io.echo(" ok ", level="ok")

        # 2. Schema — created via schema.sql (which also issues inline GRANTs).
        #    Before importing schema.sql, ensure the ``casino`` schema is
        #    owned by the dedicated ``zoid6`` role so that
        #    ``manage_schema_priv`` (used in step 3 below, also owned by
        #    ``zoid6``) can GRANT on it. See ``checkcasino.py`` for the
        #    rationale and the allow-list gate.
        if checkcasino.main(args, conn=conn) is False:
            io.echo("fail", level="error")
            return False

        io.echo("schema {var:valuecolor}casino{var:labelcolor}: ", end="")
        if database.schemaexists(args, "casino", conn=conn) is False:
            io.echo("import ", end="")
            if (
                database.importsql(args, "schema.sql", conn=conn, package="casino.sql")
                is False
            ):
                io.echo("fail", level="error")
                return False
        io.echo(" ok ", level="ok")

        # 3. Schema privs — hybrid: schema.sql also issues inline GRANTs,
        #    but we re-assert here so privs survive a schema created by any
        #    other path (manual psql, bootstrap_opencode.sql, etc.).
        #    Roles are assumed to already exist (bbsengine6.checkroles).
        for role in ("web", "term", "sysop", "opencode"):
            io.echo(
                f"{{var:labelcolor}}priv casino.{{var:valuecolor}}USAGE"
                f"{{var:labelcolor}} -> {{var:valuecolor}}{role}{{var:labelcolor}}: ",
                end="",
            )
            if (
                database.manage_schema_priv(
                    args, "grant", "usage", "casino", role, conn=conn
                )
                is False
            ):
                io.echo("fail", level="error")
                return False
            io.echo(" ok ", level="ok")

        io.echo(
            "{{var:labelcolor}}priv casino.{{var:valuecolor}}CREATE"
            "{{var:labelcolor}} -> {{var:valuecolor}}sysop{{var:labelcolor}}: ",
            end="",
        )
        if (
            database.manage_schema_priv(
                args, "grant", "create", "casino", "sysop", conn=conn
            )
            is False
        ):
            io.echo("fail", level="error")
            return False
        io.echo(" ok ", level="ok")

        # 4. Classes — 26 entries, ordered for FK resolution.
        #    Each (class, sql_file) is checked via classexists and skipped
        #    if already present.  Migration files
        #    (hidden_table_migration.sql, table_shoe_migration.sql) are
        #    deliberately omitted — their columns are already in
        #    table.sql:14-15,19.
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
            # bank_migration.sql must follow table.sql — its FKs reference
            # casino.__table(moniker) and bank.__account(id).
            ("casino.__bank_table", "bank_table.sql"),
            ("casino.bank_table", "bank_table.sql"),
            ("casino.__bank_player", "bank_player.sql"),
            ("casino.bank_player", "bank_player.sql"),
            ("casino.__banktransaction", "bank_migration.sql"),
            ("casino.banktransaction", "bank_migration.sql"),
            ("casino.__tabletransfer", "bank_migration.sql"),
            ("casino.tabletransfer", "bank_migration.sql"),
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

        return failcount == 0


