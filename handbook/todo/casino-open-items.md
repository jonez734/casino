# Casino: open items and gaps

Status: open (2026-11-05). Everything below is committed locally in `casino/`, `bbsengine6/`, and `bed/`. Nothing is pushed.

## Run against zoid6 (you run these; they need your shell as jam)

- [ ] Live spin check on `zoid6`: play one spin as a test member, then confirm one new `casino.__slot_spin` row and one `bank.__transaction` row for that spin.
- [ ] Confirm the install sequence on `zoid6` still matches `startup/main.py` if `casino --install` is ever run again (the settle function is now part of it, and `slots.sql` now has `correlation_id`).
- [ ] Check `zoid6test` is the only database `scripts/check-spin-retry.py` has been run against. It inserts and deletes rows, so never run it against `zoid6`.

## Money and correctness

- [x] **Retry dedupe is not active for real retries (found in review). Fixed: f06678f, cf5b79e, a9fa448.**
      The client sends an `idempotency_key` per spin; the server uses it as the correlation id. `handle_spin` in
      `services/slots.py` generates `correlation_id = uuid.uuid4().hex` on every call (line ~179), so a
      client retry sends a new id and the database dedupe never matches. The dedupe only protects a
      retry that reuses the id, which the current code never sends. Fix: the client sends an
      idempotency key with each spin, and the server uses it as the correlation id. Needs a protocol
      decision (client change).
- [x] **A committed settle can still reply `service_error`** (fixed: a duplicate returns the stored spin, f06678f) (`services/slots.py` lines ~257–260). The
      money has moved, but the player is told the spin failed. Fix: when the database returns
      `duplicate: true`, return the stored spin, not an error.

- [ ] `service_error` after a committed settle: if the reply fails after `engine.casino_settle_spin` commits, the player sees `service_error` for a spin that happened. A retry is now safe (dedupe on `correlation_id`), but the player is told the spin failed. Fix: on a duplicate, return the stored result instead of an error.
- [ ] Retry without the stored result: a client that retries gets `duplicate: true` with the balance, but not the reels or payout of the original spin. Decide whether the client needs them.
- [ ] Concurrency backstop: dedupe relies on the account lock. The unique index on `correlation_id` is only a backstop for a spin that settles against a different account. Confirm no such path exists.

## Review before deploy (shared production code)

- [ ] `services/slots.py`: settlement result is now read by column name (`row.get("casino_settle_spin")`), with a positional fallback for tuple rows. Review whether the fallback is still needed.
- [ ] `api/_auth.py`: a valid wire token is bound to a password session that has no token, but only when its moniker matches the session member. Review the match rule and the no-replace rule.
- [ ] `sql/casino_settle_spin_functions.sql`: dedupe check added before any balance change. Review the lock order.
- [ ] `sql/migrate_slot_spin_correlation.sql`: new migration. Confirm it is listed in whatever runs migrations for the install (`bbsengine6/scripts/run-migrations.sh` does not cover casino's sql directory).

## Test gaps

- [ ] Spectator spin test now runs with real signed tokens and bed's token store. The test depends on `engine.__bed_token`, `bank.__account`, and `casino.__table`/`__member` rows in the test database.
- [ ] `test_spin_retry_no_double_settle.py` runs the checker only when `CASINO_TEST_DB` is set. In CI it is skipped unless that is set.
- [ ] 79 casino tests are skipped (last full run: 1782 passed, 79 skipped) (gated on database, bed, or environment). Review which ones should run in CI.
- [ ] No live test of the bed WebSocket path for `slot_spin` (bed's `CasinoService` does not route it; casino's own router handles it).

## Pre-existing issues (not yet fixed)

- [ ] Blackjack and poker tests share fixed moniker prefixes (`bjbed_*`). A test that fails partway can leave rows that collide on rerun. The poker lobby test now cleans its bank mapping; check the others do the same.
- [ ] `casino/scripts/check-spin-retry.py` leaves rows behind if it is killed mid-run (cleanup is in `finally`, but a hard kill skips it). Remove the `retrychk_*` rows from `zoid6test` if a run is interrupted.

## Related, outside casino

- [ ] `bbsengine6`: VTE `RGB` XTGETTCAP reply value meaning (8 bits per component) is unverified against the xterm spec.
- [ ] `bbsengine6`: screen echo of late DA/DCS replies in cooked mode. Needs a tty-mode design decision.
- [ ] `bed`: the 11 `zoid6`-ownership test failures were fixed (commit `6e6af8a`), but the commit message repeats a wrong claim that the owner migration misses `bed_*` functions. It does not (verified in `zoid6`: zero `engine`/`bank` objects owned by anyone but `zoid6`).
- [ ] All repos: nothing pushed. Push from your terminal when ready (`bbsengine6`, `bed`, `casino`).
