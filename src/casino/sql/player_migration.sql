-- player_migration.sql
-- Migration: drop the legacy `id` bigserial PK on casino.__player and
-- promote `moniker citext NOT NULL PRIMARY KEY` to the new key model.
--
-- Idempotent (uses existence-guards on every ALTER and on the data
-- delete). Run AFTER casino.sql so casino.__player exists. Re-runnable.
--
-- Why this drops existing rows:
--   The pre-migration table allowed any number of rows per member (1:1
--   by convention, not by constraint) with no `moniker` column at all.
--   Promoting `moniker` to a NOT NULL PK requires a value on every row.
--   Per operator decision (NOT NULL, no backfill, drop existing row),
--   we DELETE rather than backfill — callers re-materialize via
--   `ensure_casino_player` on next access, which INSERTs
--   `moniker = membermoniker`, so the seeded 1:1 shape recovers.

\echo player_migration: deleting existing casino.__player rows (only if legacy id column still present)
DO $purge$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'casino'
          AND table_name = '__player'
          AND column_name = 'id'
    ) THEN
        DELETE FROM casino.__player;
    END IF;
END
$purge$;

\echo player_migration: dropping legacy id bigserial PK
DO $dropid$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'casino'
          AND table_name = '__player'
          AND column_name = 'id'
    ) THEN
        ALTER TABLE casino.__player DROP COLUMN id CASCADE;
    END IF;
END
$dropid$;

\echo player_migration: adding moniker citext NOT NULL PRIMARY KEY
DO $addmoniker$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'casino'
          AND table_name = '__player'
          AND column_name = 'moniker'
    ) THEN
        ALTER TABLE casino.__player
            ADD COLUMN moniker citext;
        ALTER TABLE casino.__player
            ALTER COLUMN moniker SET NOT NULL;
        ALTER TABLE casino.__player
            ADD CONSTRAINT pk_player_moniker PRIMARY KEY (moniker);
    END IF;
END
$addmoniker$;

\echo player_migration: done
