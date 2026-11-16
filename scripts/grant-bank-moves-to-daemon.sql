-- casino/scripts/grant-bank-moves-to-daemon.sql
--
-- Lets the zoid6 daemon move money through the bank: a bet, a payout, an insurance or split/double stake each debit one
-- bank account and credit another, and record both sides in bank.__transaction (casino.dal.bet._bank_move). The daemon
-- runs those as bed_zoid6 (dal/conn.py), which had only SELECT on the bank, so every move is refused with "permission
-- denied for table __account".
--
-- Scoped to exactly what _bank_move does: UPDATE the balance on bank.__account, INSERT into bank.__transaction with
-- its id sequence, and SELECT on casino.__bank_table to resolve a table to its account. No DELETE.
--
-- Confirm the login role the daemon connects as:
--     sudo -u postgres psql zoid6 -tAc "select usename, count(*) from pg_stat_activity where datname='zoid6' group by 1;"
--
-- Review, then run ONCE as the database owner (postgres or sysop), against the zoid6 database:
--
--     sudo -u postgres psql zoid6 -f casino/scripts/grant-bank-moves-to-daemon.sql
--
-- It is idempotent: granting an existing privilege does nothing. It adds no role and no password.

GRANT UPDATE ON bank.__account TO bed_zoid6;
GRANT INSERT ON bank.__transaction TO bed_zoid6;
GRANT USAGE, SELECT ON SEQUENCE bank.__transaction_id_seq TO bed_zoid6;

-- A bet's table side resolves through the table-to-bank mapping (casino.__bank_table), read only.
GRANT SELECT ON casino.__bank_table TO bed_zoid6;
