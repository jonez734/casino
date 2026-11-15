-- casino/scripts/grant-blackjack-round-to-daemon.sql
--
-- Lets the zoid6 daemon's login role (bed_zoid6) run a blackjack round: place a bet, deal, act, and settle.
-- Casino's connections keep the login role (dal/conn.py), and these tables are granted only to term and sysop,
-- so the daemon's inserts and updates are denied ("permission denied for table __game").
--
-- This covers the tables the round touches. map_cardtable_player (the seat) has its own grant script,
-- grant-table-join-to-daemon.sql, which must be run too.
--
-- Review, then run ONCE as the database owner (postgres or sysop), against the zoid6 database:
--
--     sudo -u postgres psql zoid6 -f casino/scripts/grant-blackjack-round-to-daemon.sql
--
-- It is idempotent. It adds no role and no password, and it does not grant DDL or drops.

GRANT SELECT, INSERT, UPDATE, DELETE ON casino.__game TO bed_zoid6;
GRANT SELECT, INSERT, UPDATE, DELETE ON casino.__hand TO bed_zoid6;
GRANT SELECT, INSERT, UPDATE, DELETE ON casino.__betlog TO bed_zoid6;
GRANT SELECT, INSERT, UPDATE, DELETE ON casino.__table TO bed_zoid6;
GRANT SELECT, INSERT, UPDATE, DELETE ON casino.__player TO bed_zoid6;
GRANT SELECT, INSERT ON casino.__shoe_event TO bed_zoid6;
GRANT SELECT, INSERT ON casino.__log TO bed_zoid6;

-- Sequences behind the generated ids of the tables the round inserts into.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA casino TO bed_zoid6;
