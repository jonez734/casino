# Slots: settle through bed's bank service, not casino's DAL

Status: closed. Settlement now goes through a casino-owned settle op.

## Problem (as found)
`services/slots.py` moved spin money with `bbsengine6.bank.BankService` over casino's DB
role. Bed's bank writes go through `engine.bed_bank_op` (SECURITY DEFINER, token-digest
gated), so slots bypassed the path every other bank operation uses.

## Decision
Option (b): a casino-owned settle op, `engine.casino_settle_spin(token_hash, args)`.
The bank move, the `casino.__slot_spin` audit row, and the player stats commit in one
function. Splitting them across bed would break that atomicity.

This is an explicit exception to "bed owns bank writes". Casino's function writes
`bank.__account` and `bank.__transaction` directly. It is accepted for slot settlement
only; it does not extend to other bank operations.

## What changed
- `sql/casino_settle_spin_functions.sql`: the op. SECURITY DEFINER, owned by zoid6.
  The acting moniker comes from `engine.__bed_token`. Granted EXECUTE to `bed_zoid6`,
  the daemon's login role, which is the role casino's connections use
  (`dal/conn.py` keeps the login role).
- `startup/main.py`: installs the op after `casino_op_functions.sql`.
- `services/slots.py`: the settlement block is one call to the op. The
  `bbsengine6.bank` import and the `bbsengine6.bank.access` gate are removed. A spin with
  no session token is refused before any SQL runs.
- Tests: `test_casino_settle_spin_functions.py` pins the contract in source. The slots
  unit, flow, and integrated tests now assert the settle payload, not the old bank trace.

## Verified against a database
Run in a rolled-back transaction on `zoid6test`, with a member, token, account, and table
fixture. Nothing persisted (checked afterwards).
- Winning spin: success, balance moved by the net, spin row written.
- Losing spin with funds: success, balance reduced by the bet.
- Overdraft: `insufficient_funds`, balance unchanged.
- Net not equal to payout minus bet: `invalid_request`.
- Push (net 0): success, balance unchanged, no bank transaction row.
- Dead or revoked token: raises `no live session`.

## Known, not caused by this change
`test_slots_table_channel.py` (3 tests) fails on the committed tree before this change,
from the `casino_table_state` join reply. Tracked separately.

## Not done
- The live `casino --install` has not been run against a real database, so the function
  is installed only in `zoid6test` by hand. The startup path is pinned by a test.
- Integration tests gated on `CASINO_TEST_DB` were not run.
