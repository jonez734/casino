-- Test data for integration tests
-- Run this after casino.sql and bank.sql

-- Set up test user 'jam' in engine
INSERT INTO engine.__member (moniker, loginid, password, email, credits)
VALUES ('jam', 'jam', crypt('test', gen_salt('md5')), 'jam@test.local', 100000)
ON CONFLICT (moniker) DO UPDATE SET password = crypt('test', gen_salt('md5')), credits = 100000;

-- Dealer is a system pseudo-member referenced by casino.__hand.playermoniker
-- (FK to engine.__member). It exists so a dealer's hand row can be
-- inserted; no password / login is needed since it never authenticates.
INSERT INTO engine.__member (moniker, loginid, password, email, credits)
VALUES ('__dealer__', '__dealer__', crypt('__no_password__', gen_salt('md5')), '__dealer__@casino.local', 0)
ON CONFLICT (moniker) DO NOTHING;

-- Set up bank account for test user
INSERT INTO bank.__account (moniker, balance, maxtransfer)
VALUES ('jam', 100000, 1000000)
ON CONFLICT (moniker) DO UPDATE SET balance = 100000;

-- Set up casino player record (legacy 1:1 shape; `moniker = membermoniker`
-- so existing `WHERE moniker = 'jam'` queries continue to find the row).
INSERT INTO casino.__player (membermoniker, moniker)
VALUES ('jam', 'jam')
ON CONFLICT (moniker) DO NOTHING;
