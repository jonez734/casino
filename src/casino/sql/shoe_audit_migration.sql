-- casino/sql/shoe_audit_migration.sql
-- Migration: persisted poker table state and the per-draw shoe audit log. Idempotent.
--
-- casino.__poker_state: one row per poker table holding the whole in-memory table (seats,
--   stacks, the hand in progress, the turn and its deadline, the shoe, the last result). It is
--   written after every action so a bed restart resumes the game. Tables are never ended by a
--   restart.
-- casino.__shoe_event: one row per shoe event, written only when casino runs with --audit.
--   kind is 'draw' or 'burn' (card set) or 'reshuffle' (card NULL). draw_count is the shoe's
--   uses after the event; shoe_size is the number of cards in a full shoe.

create table if not exists casino.__poker_state (
    "tablemoniker" citext primary key references casino.__table(moniker) on update cascade on delete cascade,
    "state"        jsonb not null,
    "updated"      timestamptz not null default now()
);

create table if not exists casino.__shoe_event (
    "id"           bigserial unique not null primary key,
    "tablemoniker" citext references casino.__table(moniker) on update cascade on delete cascade,
    "handid"       bigint,
    "kind"         text not null check (kind in ('draw', 'burn', 'reshuffle')),
    "card"         text,
    "draw_count"   integer not null,
    "shoe_size"    integer not null,
    "created"      timestamptz not null default now(),
    check ((kind = 'reshuffle') = (card is null))
);

create index if not exists idx_shoe_event_table
    on casino.__shoe_event (tablemoniker, id);

-- Grants: bed (the daemon) reads and writes both tables; web only reads the audit log.
grant select, insert, update, delete on casino.__poker_state to bed;
grant select, insert on casino.__shoe_event to bed;
grant select on casino.__shoe_event to web;
grant all on casino.__poker_state to term, sysop;
grant all on casino.__shoe_event to term, sysop;
grant usage, select on casino.__shoe_event_id_seq to bed;
grant select on casino.__shoe_event_id_seq to web;
grant all on casino.__shoe_event_id_seq to term, sysop;

-- bed updates shoe state on casino.__table for poker tables too.
grant select, update on casino.__table to bed;

-- The developer test role (opencode and its m_ data role) gets the same full DML on the new
-- tables that it already has on casino.__table and casino.__game, so the test suites can run.
grant select, insert, update, delete on casino.__poker_state to opencode, m_opencode;
grant select, insert, update, delete on casino.__shoe_event to opencode, m_opencode;
grant usage, select on casino.__shoe_event_id_seq to opencode, m_opencode;
