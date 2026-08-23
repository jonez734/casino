-- casino.__player holds per-casino-player state (lastplayed, attrs, stats)
-- keyed by a globally-unique player moniker (`moniker citext NOT NULL PK`)
-- with `membermoniker` as a FK to engine.__member(moniker). Each
-- engine.__member row may own many casino.__player rows (one per
-- `moniker`), so a single BBS account can play multiple casino
-- identities. Existing 1:1 callers keep working because
-- `ensure_casino_player` INSERTs `moniker = membermoniker` on the
-- lazy-materialize path, so the legacy `WHERE moniker = <membermoniker>`
-- queries still find the single seeded row.
--
-- Migration: see player_migration.sql (drops the legacy `id`
-- bigserial PK, drops existing rows so the NOT NULL constraint can
-- land clean, then promotes `moniker` to the new PK).
create table if not exists casino.__player (
    "membermoniker" citext constraint fk_player_membermoniker references engine.__member(moniker) on update cascade on delete set null,
    "moniker" citext not null primary key,
    "location" text,
    "lastplayed" timestamptz,
    "attrs" jsonb,
    "stats" jsonb default '{}'::jsonb
);

grant select on casino.__player to web, term, sysop;
grant all on casino.__player to term, sysop;
