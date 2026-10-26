-- casino/sql/map_cardtable_player_migration.sql
-- Migration: add joinedat to casino.map_cardtable_player.
--
-- casino.map_cardtable_player was created before joinedat existed. Its class file
-- (map_cardtable_player.sql) is skipped on an existing install (classexists), and
-- create table if not exists does not add columns, so the live table never got the
-- column. The table functions (casino_read_functions.sql) order seated players by
-- joinedat, so this migration must run before them. Idempotent.

alter table casino.map_cardtable_player
    add column if not exists "joinedat" timestamptz default now();
