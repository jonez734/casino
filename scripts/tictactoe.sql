-- casino/scripts/tictactoe.sql
-- Tic-tac-toe v1 schema delta.
--
-- As of v1, the casino.__table.type column is unconstrained TEXT, so no
-- ALTER TABLE is required to accept the value 'tictactoe'. This file is
-- kept as an anchor for future tictactoe-specific schema changes (e.g.
-- replay history, leaderboards, etc.).
--
-- Run only if you want to add the tictactoe-specific tables in the future:
--   psql -d zoid6 -U postgres -f tictactoe.sql

-- (no schema changes in v1)

-- Verify the column accepts the new type:
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'casino'
          AND table_name = '__table'
          AND column_name = 'type'
    ) THEN
        RAISE EXCEPTION 'casino.__table.type column not found';
    END IF;
    -- 'tictactoe' is accepted because type is unconstrained text.
    RAISE NOTICE 'casino.__table.type accepts tictactoe (unconstrained text)';
END $$;
