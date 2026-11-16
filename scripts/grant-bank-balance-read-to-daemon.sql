-- casino/scripts/grant-bank-balance-read-to-daemon.sql
--
-- Lets the zoid6 daemon read a member's bank account balance, so a member with no recorded credits takes it
-- (casino.dal.player.mirror_credits_from_bank). The bet path runs that mirror as bed_zoid6 (see dal/conn.py), which had
-- no access to the bank schema: "permission denied for schema bank".
--
-- Scoped to what the mirror uses: USAGE on the bank schema, and SELECT on bank.__account only. The daemon does not
-- need to change a bank balance here, so no write is granted.
--
-- Confirm the login role the daemon connects as:
--     sudo -u postgres psql zoid6 -tAc "select usename, count(*) from pg_stat_activity where datname='zoid6' group by 1;"
--
-- Review, then run ONCE as the database owner (postgres or sysop), against the zoid6 database:
--
--     sudo -u postgres psql zoid6 -f casino/scripts/grant-bank-balance-read-to-daemon.sql
--
-- It is idempotent: granting an existing privilege does nothing. It adds no role and no password.

GRANT USAGE ON SCHEMA bank TO bed_zoid6;
GRANT SELECT ON bank.__account TO bed_zoid6;
