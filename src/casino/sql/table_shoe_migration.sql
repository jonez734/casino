-- Migration: Add shoe_cards and shoe_uses columns to casino.__table
-- Run this to fix: column "shoe_cards" does not exist

ALTER TABLE casino.__table ADD COLUMN IF NOT EXISTS "shoe_cards" text[] default null;
ALTER TABLE casino.__table ADD COLUMN IF NOT EXISTS "shoe_uses" integer default 0;
