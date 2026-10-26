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
