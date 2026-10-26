-- casino/sql/table_turn_seconds_migration.sql
-- Migration: the play clock. turn_seconds is the seconds a human seat has to act; 0 means no clock.
-- The sysop ceiling is config (casino.clock.max_turn_seconds in bed.json); the bed handler refuses
-- a value above it, so the database stores what it is given. Existing tables default to 0 (off).
-- Idempotent.

alter table casino.__table
    add column if not exists "turn_seconds" integer not null default 0;

alter table casino.__table
    drop constraint if exists chk_table_turn_seconds;
alter table casino.__table
    add constraint chk_table_turn_seconds check (turn_seconds >= 0);

-- The penalty when a round's clock expires: 'skip' (the hand stands on its current cards and the
-- round settles as normal) or 'remove' (the hand is removed from the round and its bet is
-- returned). Default 'skip'. The owner sets it per table; the value is checked here.
alter table casino.__table
    add column if not exists "clock_penalty" text not null default 'skip';

alter table casino.__table
    drop constraint if exists chk_table_clock_penalty;
alter table casino.__table
    add constraint chk_table_clock_penalty check (clock_penalty in ('skip', 'remove'));
