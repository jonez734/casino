-- casino/sql/hidden_table_migration.sql
-- Migration: Add hidden column to casino.__table for hidden table support
--
-- Hidden tables don't appear in list_tables for non-sysop users.
-- Users must know the exact table moniker to join.
-- Sysops always see hidden tables in list (with hidden=true indicator)
-- and can join hidden tables without restriction.

ALTER TABLE casino.__table ADD COLUMN IF NOT EXISTS "hidden" boolean DEFAULT false;

create index if not exists idx_table_hidden on casino.__table(hidden);
