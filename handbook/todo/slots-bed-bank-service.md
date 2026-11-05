# Slots: settle through bed's bank service, not casino's DAL

## Problem
`casino/src/casino/services/slots.py` moves spin money with
`bbsengine6.bank.BankService` (add_funds / remove_funds / get_balance)
over casino's DB role. Bed's bank writes go through
`engine.bed_bank_op` (SECURITY DEFINER, token-digest gated). Slots
bypasses that path, so the bank writes and the access gate for slots
differ from every other bank operation.

## Goal
Slots settles the bet and payout through bed's bank service
(`engine.bed_bank_op` or a bed-owned settle op), with the acting
moniker taken from the verified token.

## Open decision
Where the atomic spin settlement lives: (a) a bed-owned op that also
writes the spin audit, (b) a casino-owned `engine.casino_op` settle
op, or (c) keep the current path and document it. Recommendation
pending.

## Acceptance
- Spin success, insufficient funds, push (net 0), revoked token,
  and rollback when the bank move fails are all tested.
- `services/slots.py` no longer imports `bbsengine6.bank`.
- Grants for any new SQL function are pinned by a test.
