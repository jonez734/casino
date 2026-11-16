-- casino/scripts/grant-leave-table-to-daemon.sql
--
-- Lets the zoid6 daemon remove a player from a table's round when they leave (or disconnect). A leave runs
-- "DELETE FROM casino.map_game_player" (dal/table.py, remove_player_from_table) over a connection that keeps the
-- login role (dal/conn.py), which the running daemon reports as bed_zoid6 in pg_stat_activity. Without this grant the
-- delete is denied: "permission denied for table map_game_player".
--
-- The same removal also reads the table's players (SELECT). This grants exactly those two privileges, and nothing
-- else: the daemon does not need to insert into or update this table.
--
-- Confirm the login role the daemon connects as:
--     sudo -u postgres psql zoid6 -tAc "select usename, count(*) from pg_stat_activity where datname='zoid6' group by 1;"
--
-- Review, then run ONCE as the database owner (postgres or sysop), against the zoid6 database:
--
--     sudo -u postgres psql zoid6 -f casino/scripts/grant-leave-table-to-daemon.sql
--
-- It is idempotent: granting an existing privilege does nothing. It adds no role and no password.

GRANT SELECT, DELETE ON casino.map_game_player TO bed_zoid6;
