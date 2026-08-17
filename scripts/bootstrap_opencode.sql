-- casino/scripts/bootstrap_opencode.sql
-- Bootstrap opencode user test database.
--
-- Run as a superuser (postgres or jam) from the casino repo root so
-- the \i path below resolves:
--   psql -d <dbname> -U postgres -f scripts/bootstrap_opencode.sql
--
-- The script assumes bbsengine6.startup has already run on the target
-- database (so the bank, engine, and base roles exist); it adds the
-- casino schema, the opencode privs, and the SECURITY DEFINER helpers
-- that scripts/setup_test_db.py invokes to seed constraints and the
-- casino:house account.

-- Change schema owners (must be superuser)
ALTER SCHEMA bank OWNER TO opencode;
ALTER SCHEMA casino OWNER TO opencode;
ALTER SCHEMA engine OWNER TO opencode;

-- Change table owners
ALTER TABLE bank.__account OWNER TO opencode;
ALTER TABLE bank.__transaction OWNER TO opencode;
ALTER TABLE bank.__transfer OWNER TO opencode;
ALTER TABLE casino.__account OWNER TO opencode;
ALTER TABLE casino.__bank_player OWNER TO opencode;
ALTER TABLE casino.__bank_table OWNER TO opencode;
ALTER TABLE casino.__banktransaction OWNER TO opencode;
ALTER TABLE casino.__game OWNER TO opencode;
ALTER TABLE casino.__hand OWNER TO opencode;
ALTER TABLE casino.__log OWNER TO opencode;
ALTER TABLE casino.__player OWNER TO opencode;
ALTER TABLE casino.__table OWNER TO opencode;
ALTER TABLE casino.__tabletransfer OWNER TO opencode;
ALTER TABLE casino.map_cardtable_player OWNER TO opencode;
ALTER TABLE casino.map_game_player OWNER TO opencode;
ALTER TABLE engine.__member OWNER TO opencode;
ALTER TABLE engine.__session OWNER TO opencode;
ALTER TABLE engine.__alert OWNER TO opencode;
ALTER TABLE engine.__folder OWNER TO opencode;
ALTER TABLE engine.__sig OWNER TO opencode;
ALTER TABLE engine.flag OWNER TO opencode;
ALTER TABLE engine.member OWNER TO opencode;
ALTER TABLE engine.session OWNER TO opencode;
ALTER TABLE engine.alert OWNER TO opencode;
ALTER TABLE engine.folder OWNER TO opencode;
ALTER TABLE engine.sig OWNER TO opencode;

-- Grant schema usage
GRANT USAGE ON SCHEMA bank TO opencode;
GRANT USAGE ON SCHEMA casino TO opencode;
GRANT USAGE ON SCHEMA engine TO opencode;

-- Grant table permissions (future tables)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA bank TO opencode;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA casino TO opencode;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA engine TO opencode;

-- Grant table permissions (existing tables)
GRANT ALL ON ALL TABLES IN SCHEMA bank TO opencode;
GRANT ALL ON ALL TABLES IN SCHEMA casino TO opencode;
GRANT ALL ON ALL TABLES IN SCHEMA engine TO opencode;

-- Grant sequence permissions (future sequences)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA bank TO opencode;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA casino TO opencode;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA engine TO opencode;

-- Grant sequence permissions (existing sequences)
GRANT ALL ON ALL SEQUENCES IN SCHEMA bank TO opencode;
GRANT ALL ON ALL SEQUENCES IN SCHEMA casino TO opencode;
GRANT ALL ON ALL SEQUENCES IN SCHEMA engine TO opencode;

-- Helper functions for constraints (if needed)
GRANT EXECUTE ON FUNCTION bank.setup_constraints() TO opencode;
GRANT EXECUTE ON FUNCTION engine.setup_member_constraints() TO opencode;

-- Security definer functions to allow opencode to modify constraints
CREATE OR REPLACE FUNCTION bank.setup_constraints()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = bank, pg_temp
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'bank.__account'::regclass 
        AND contype = 'f'
    ) THEN
        ALTER TABLE bank.__account DROP CONSTRAINT fk_bankaccount_member;
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
        ALTER TABLE bank.__account ADD COLUMN overdraft_limit numeric(10,0) default 100000;
    END IF;

    UPDATE bank.__account SET overdraft_limit = 100000 WHERE moniker = 'casino:house' AND overdraft_limit IS NULL;
END;
$$;

CREATE OR REPLACE FUNCTION engine.setup_member_constraints()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = engine, pg_temp
AS $$
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
$$;

-- Install citext (required by casino.__player.membermoniker and
-- casino.__bank_player.membermoniker).
CREATE EXTENSION IF NOT EXISTS citext;

-- Bootstrap casino schema via the canonical driver. This is the same
-- driver casino.startup.main uses via importsql, so a new casino table
-- added to src/casino/sql/casino.sql flows through both bootstrap
-- paths automatically. Order matters: this must run before the stats
-- migration below so casino.__player exists.
\i 'src/casino/sql/casino.sql'

-- Add stats JSONB column to __player if not exists.
ALTER TABLE casino.__player ADD COLUMN IF NOT EXISTS stats jsonb default '{}'::jsonb;
