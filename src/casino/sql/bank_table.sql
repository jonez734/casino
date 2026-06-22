-- Table bank account mapping (table's bank account linked to owner's bank)
CREATE TABLE IF NOT EXISTS casino.__bank_table (
    table_moniker citext primary key,
    bank_account_id bigint references bank.__account(id),
    created timestamptz default now()
);

CREATE OR REPLACE VIEW casino.bank_table AS
SELECT 
    bt.*,
    timezone(currentmember.tz, bt.created) as createdlocal
FROM casino.__bank_table bt
LEFT OUTER JOIN engine.__member currentmember ON (currentmember.loginid = current_user);

GRANT SELECT ON casino.bank_table TO web, term;
GRANT ALL ON casino.__bank_table TO sysop;
