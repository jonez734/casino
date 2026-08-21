-- casino/src/casino/sql/bootstrap_zoid6.sql
-- Bootstrap zoid6 user test database. Idempotent; safe to re-run.
--
-- Run as a superuser (postgres or jam). This script lives in the same
-- directory as the canonical casino driver (casino.sql), so the bare
-- \i casino.sql below resolves via psql's CWD. Invoke with psql CWD
-- set to this directory so the inner bare-relative \i paths inside
-- casino.sql (schema.sql, player.sql, etc.) also resolve correctly:
--
--     cd casino/src/casino/sql
--     psql -d <dbname> -U postgres -f bootstrap_zoid6.sql
--
-- Assumes the 'zoid6' PostgreSQL role already exists (created by
-- `bbsengine6.startup` or by hand).  Existence-guarded everywhere so
-- missing bank/engine schemas no-op cleanly on a fresh DB; the casino
-- schema is bootstrapped unconditionally from casino.sql.

-- ===== Install citext (required by casino.__player.membermoniker
--      and casino.__bank_player.membermoniker) =====
CREATE EXTENSION IF NOT EXISTS citext;

-- ===== Bootstrap casino schema (creates it if missing) =====
\i casino.sql

-- ===== Stats migration (existence-guarded) =====
-- On a totally fresh DB without the bank/engine schemas, the casino
-- driver above fails partway (FKs to engine.__member etc.), so
-- casino.__player may not exist yet.  No-op cleanly in that case; a
-- fully-populated test DB will run bbsengine6.startup before this
-- script and casino.__player will exist.
DO $stats$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'casino' AND c.relname = '__player'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'casino'
        AND table_name = '__player'
        AND column_name = 'stats'
    ) THEN
        ALTER TABLE casino.__player
        ADD COLUMN stats jsonb default '{}'::jsonb;
    END IF;
END
$stats$;

-- ===== Schema owners, table owners, GRANTs (existence-guarded) =====
-- One DO block iterates over bank/engine/casino and applies the full
-- set of zoid6-level grants for every schema that exists.  Table
-- ownership is set for every table in each schema (information_schema
-- query, not a hard-coded list, so newly-added tables get picked up
-- when the script is re-run).
DO $bootstrap$
DECLARE
    sname text;
    table_rec record;
BEGIN
    FOR sname IN SELECT unnest(ARRAY['bank', 'engine', 'casino']) LOOP
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = sname) THEN
            EXECUTE format('ALTER SCHEMA %I OWNER TO zoid6', sname);
            EXECUTE format('GRANT USAGE ON SCHEMA %I TO zoid6', sname);
            EXECUTE format(
                'GRANT SELECT, INSERT, UPDATE, DELETE '
                'ON ALL TABLES IN SCHEMA %I TO zoid6',
                sname
            );
            EXECUTE format(
                'GRANT ALL ON ALL TABLES IN SCHEMA %I TO zoid6',
                sname
            );
            EXECUTE format(
                'GRANT USAGE, SELECT ON ALL SEQUENCES '
                'IN SCHEMA %I TO zoid6',
                sname
            );
            EXECUTE format(
                'GRANT ALL ON ALL SEQUENCES IN SCHEMA %I TO zoid6',
                sname
            );

            FOR table_rec IN
                SELECT quote_ident(table_schema)
                       || '.'
                       || quote_ident(table_name) AS qualified
                FROM information_schema.tables
                WHERE table_schema = sname
            LOOP
                EXECUTE format(
                    'ALTER TABLE %s OWNER TO zoid6', table_rec.qualified
                );
            END LOOP;
        END IF;
    END LOOP;
END
$bootstrap$;

-- ===== Helper functions (bank + engine; existence-guarded) =====
-- These SECURITY DEFINER helpers are invoked by
-- scripts/setup_test_db.py to apply test-DB-specific constraints and
-- to seed the casino:house bank account.
DO $helpers$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'bank') THEN
        CREATE OR REPLACE FUNCTION bank.setup_constraints()
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = bank, pg_temp
        AS $bankfn$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'bank.__account'::regclass
                AND contype = 'f'
            ) THEN
                ALTER TABLE bank.__account
                DROP CONSTRAINT fk_bankaccount_member;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'bank.__account'::regclass
                AND conname = 'chk_bankaccount_moniker_format'
            ) THEN
                ALTER TABLE bank.__account
                ADD CONSTRAINT chk_bankaccount_moniker_format
                CHECK (
                    moniker ~ '^[a-zA-Z0-9_]+$'
                    OR moniker ~ '^[a-zA-Z0-9_]+:[a-zA-Z0-9_]+$'
                );
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'bank'
                AND table_name = '__account'
                AND column_name = 'overdraft_limit'
            ) THEN
                ALTER TABLE bank.__account
                ADD COLUMN overdraft_limit numeric(10,0) default 100000;
            END IF;

            UPDATE bank.__account
            SET overdraft_limit = 100000
            WHERE moniker = 'casino:house' AND overdraft_limit IS NULL;
        END;
        $bankfn$;

        GRANT EXECUTE ON FUNCTION bank.setup_constraints() TO zoid6;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'engine') THEN
        CREATE OR REPLACE FUNCTION engine.setup_member_constraints()
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = engine, pg_temp
        AS $enginefn$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'engine.__member'::regclass
                AND conname = 'chk_member_moniker_format'
            ) THEN
                ALTER TABLE engine.__member
                ADD CONSTRAINT chk_member_moniker_format
                CHECK (moniker ~ '^[a-zA-Z0-9_]+$');
            END IF;
        END;
        $enginefn$;

        GRANT EXECUTE ON FUNCTION engine.setup_member_constraints() TO zoid6;
    END IF;
END
$helpers$;
