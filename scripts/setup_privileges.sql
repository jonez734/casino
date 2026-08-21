-- casino/scripts/setup_privileges.sql
-- Helper functions to allow zoid6 to modify constraints (run once as sysop)

-- Function to allow zoid6 to add/drop constraints on bank.__account
-- Run this as sysop/postgres ONE TIME to create the helper

CREATE OR REPLACE FUNCTION bank.setup_constraints()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = bank, pg_temp
AS $$
BEGIN
    -- Drop FK constraint if it exists
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'bank.__account'::regclass 
        AND contype = 'f'
    ) THEN
        ALTER TABLE bank.__account DROP CONSTRAINT fk_bankaccount_member;
    END IF;

    -- Add CHECK constraint if not exists
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

    -- Add overdraft_limit column if not exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'bank' 
        AND table_name = '__account' 
        AND column_name = 'overdraft_limit'
    ) THEN
        ALTER TABLE bank.__account ADD COLUMN overdraft_limit numeric(10,0) default 100000;
    END IF;

    -- Update house account with overdraft limit
    UPDATE bank.__account SET overdraft_limit = 100000 WHERE moniker = 'casino:house' AND overdraft_limit IS NULL;
END;
$$;

-- Function to allow zoid6 to add constraint on engine.__member
CREATE OR REPLACE FUNCTION engine.setup_member_constraints()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = engine, pg_temp
AS $$
BEGIN
    -- Add CHECK constraint if not exists
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

-- Grant execute on functions to zoid6
GRANT EXECUTE ON FUNCTION bank.setup_constraints() TO zoid6;
GRANT EXECUTE ON FUNCTION engine.setup_member_constraints() TO zoid6;

-- Grant table permissions to zoid6
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA bank TO zoid6;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA casino TO zoid6;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA engine TO zoid6;

-- Grant sequence permissions to zoid6
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA bank TO zoid6;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA casino TO zoid6;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA engine TO zoid6;

-- Grant schema usage
GRANT USAGE ON SCHEMA bank TO zoid6;
GRANT USAGE ON SCHEMA casino TO zoid6;
GRANT USAGE ON SCHEMA engine TO zoid6;
