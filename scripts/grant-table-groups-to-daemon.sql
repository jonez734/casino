-- casino/scripts/grant-table-groups-to-daemon.sql
--
-- Lets the zoid6 daemon keep each casino table's message group in step with its seats. A seat or leave calls
-- casino.tablegroups, which runs bbsengine6.message against engine.__message_group, engine.__message_group_member
-- and engine.__message_source as the login role bed_zoid6 (see dal/conn.py). Without these grants each call is
-- denied: "permission denied for table __message_group". The seat itself is not affected (it is already
-- removed), but the group update is refused, and the leave waits on it until it fails.
--
-- Scoped to exactly what casino.tablegroups uses: the group and its members, and the bot dealer's named source.
-- Nothing else on the message tables is granted.
--
-- Confirm the login role the daemon connects as:
--     sudo -u postgres psql zoid6 -tAc "select usename, count(*) from pg_stat_activity where datname='zoid6' group by 1;"
--
-- Review, then run ONCE as the database owner (postgres or sysop), against the zoid6 database:
--
--     sudo -u postgres psql zoid6 -f casino/scripts/grant-table-groups-to-daemon.sql
--
-- It is idempotent: granting an existing privilege does nothing. It adds no role and no password.

GRANT SELECT, INSERT, UPDATE, DELETE ON engine.__message_group TO bed_zoid6;
GRANT SELECT, INSERT, UPDATE, DELETE ON engine.__message_group_member TO bed_zoid6;
GRANT SELECT, INSERT, UPDATE, DELETE ON engine.__message_source TO bed_zoid6;

-- The inserts draw the new row's id from these sequences.
GRANT USAGE, SELECT ON SEQUENCE engine.__message_group_id_seq TO bed_zoid6;
GRANT USAGE, SELECT ON SEQUENCE engine.__message_group_member_id_seq TO bed_zoid6;
