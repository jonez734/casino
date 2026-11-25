-- Casino credits-to-coins ratio as two positive integers (ratio_num credits per ratio_den coins).
-- Replaces the single numeric(4,2) credits_to_dollars_ratio, which cannot hold a (num, den) pair.
-- The default is 1:1, the old 1.00. No rows and no code read the old column, so it is left in place and unused.
ALTER TABLE casino.__bank_player
    ADD COLUMN IF NOT EXISTS ratio_num integer NOT NULL DEFAULT 1 CHECK (ratio_num > 0),
    ADD COLUMN IF NOT EXISTS ratio_den integer NOT NULL DEFAULT 1 CHECK (ratio_den > 0);
