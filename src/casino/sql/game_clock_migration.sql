-- casino/sql/game_clock_migration.sql
-- Migration: the round clock (blackjack, simultaneous hands). A round's action_deadline is the
-- time the open hands must act by; NULL means no clock is running. The table's turn_seconds sets
-- the length; the penalty (skip or remove) is applied to each unfinished hand on expiry. Stored on
-- the round so a reconnect sees the same deadline. Idempotent.

alter table casino.__game
    add column if not exists "action_deadline" timestamptz;

create index if not exists idx_game_action_deadline
    on casino.__game (action_deadline)
    where action_deadline is not null;
