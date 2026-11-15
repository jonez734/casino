-- casino/scripts/grant-table-join-to-daemon.sql
--
-- Lets the zoid6 daemon seat a player at a cash table. A join runs
-- "INSERT INTO casino.map_cardtable_player" (dal/table.py) over a connection that keeps the login role
-- (dal/conn.py), which the running daemon reports as bed_zoid6 in pg_stat_activity. Without this grant the
-- insert is denied: "permission denied for table map_cardtable_player".
--
-- Confirm the login role the daemon connects as:
--     sudo -u postgres psql zoid6 -tAc "select usename, count(*) from pg_stat_activity where datname='zoid6' group by 1;"
--
-- Review, then run ONCE as the database owner (postgres or sysop), against the zoid6 database:
--
--     sudo -u postgres psql zoid6 -f casino/scripts/grant-table-join-to-daemon.sql
--
-- It is idempotent: granting an existing privilege does nothing. It adds no role and no password.

-- The daemon's login role (bed_zoid6) must hold the seat insert the join makes. Granting to it directly keeps
-- the change to the one role the daemon uses; the existing term/sysop grants already cover people.
GRANT SELECT, INSERT, UPDATE, DELETE ON casino.map_cardtable_player TO bed_zoid6;

-- Read access the join uses to check seats. (The insert uses the table's own columns: no sequence grant is
-- needed, since the seat row has no generated id.)
GRANT SELECT ON casino.map_cardtable_player TO bed_zoid6;
