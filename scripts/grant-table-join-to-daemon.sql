-- casino/scripts/grant-table-join-to-daemon.sql
--
-- Lets the zoid6 daemon's database role seat a player at a cash table. A join runs
-- "INSERT INTO casino.map_cardtable_player" (dal/table.py), and the daemon connects as the
-- role named in bed.json (database.user, currently "bed"). Without this grant the insert is
-- denied: "permission denied for table map_cardtable_player".
--
-- Confirm the role exists first:
--     sudo -u postgres psql zoid6 -c "\du zoid6"
--
-- Review, then run ONCE as the database owner (postgres or sysop), against the zoid6 database:
--
--     sudo -u postgres psql zoid6 -f casino/scripts/grant-table-join-to-daemon.sql
--
-- It is idempotent: granting an existing privilege does nothing. It adds no role and no password.

-- The daemon's role must hold the table grants the join needs. Granting to zoid6 directly keeps the change
-- to the one role the daemon uses; the existing term/sysop grants already cover people.
GRANT SELECT, INSERT, UPDATE, DELETE ON casino.map_cardtable_player TO zoid6;

-- Its sequence (if any) and the membership checks the join reads.
GRANT SELECT ON casino.map_cardtable_player TO zoid6;
