-- Player account in casino (links to bank for real $, stores casino credits)
CREATE TABLE IF NOT EXISTS casino.__bank_player (
    player_moniker citext primary key references engine.__member(moniker) on delete cascade,
    bank_account_id bigint references bank.__account(id),
    credits numeric(10,0) default 0,
    credits_to_dollars_ratio numeric(4,2) default 1.00,
    plays_on_house boolean default false,
    high_roller boolean default false,
    created timestamptz default now()
);

CREATE OR REPLACE VIEW casino.bank_player AS
SELECT 
    bp.*,
    timezone(currentmember.tz, bp.created) as createdlocal
FROM casino.__bank_player bp
LEFT OUTER JOIN engine.__member currentmember ON (currentmember.loginid = current_user);

GRANT SELECT ON casino.bank_player TO web, term;
GRANT ALL ON casino.__bank_player TO sysop;
