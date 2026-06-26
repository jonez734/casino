-- Test data for integration tests
-- Run this after casino.sql and bank.sql

-- Set up test user 'jam' in engine
INSERT INTO engine.__member (moniker, loginid, password, email, credits)
VALUES ('jam', 'jam', crypt('test', gen_salt('md5')), 'jam@test.local', 100000)
ON CONFLICT (moniker) DO UPDATE SET password = crypt('test', gen_salt('md5')), credits = 100000;

-- Set up bank account for test user
INSERT INTO bank.__account (moniker, balance, maxtransfer)
VALUES ('jam', 100000, 1000000)
ON CONFLICT (moniker) DO UPDATE SET balance = 100000;

-- Set up casino player record
INSERT INTO casino.__player (moniker, wins, losses, pushes, blackjacks, net)
VALUES ('jam', 0, 0, 0, 0, 0)
ON CONFLICT (moniker) DO UPDATE SET wins = 0, losses = 0, pushes = 0, blackjacks = 0, net = 0;
