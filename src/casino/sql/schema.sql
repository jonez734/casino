create schema if not exists casino;
grant usage on schema casino to sysop, web, term, opencode;

-- Create casino house account if not exists
-- (This requires bank schema permissions - skip if not available)
-- insert into bank.__account (moniker, balance, maxtransfer) 
-- values ('casino:house', 0, 1000000)
-- on conflict (moniker) do nothing;
