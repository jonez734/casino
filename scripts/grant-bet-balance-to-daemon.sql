-- casino/scripts/grant-bet-balance-to-daemon.sql
--
-- Lets the zoid6 daemon's login role (bed_zoid6) take and pay bets. A bet debits engine.__member.credits, and a
-- payout credits it (dal/bet.py, services/game.py). engine.__member is the engine's identity table; the
-- daemon's login role has no write access to it, so the balance update is denied ("permission denied for
-- table __member").
--
-- This grants the minimum the bet needs: read the row, and update only the credits column. It does not grant
-- update on the member's other columns (password, email, approval, roles).
--
-- Review, then run ONCE as the database owner (postgres or sysop), against the zoid6 database:
--
--     sudo -u postgres psql zoid6 -f casino/scripts/grant-bet-balance-to-daemon.sql
--
-- It is idempotent. It adds no role and no password.

GRANT SELECT ON engine.__member TO bed_zoid6;
GRANT UPDATE (credits) ON engine.__member TO bed_zoid6;
