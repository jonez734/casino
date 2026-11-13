# casino — front-end seam, blackjack and per-application sections

> **Last updated:** 2026-11-11.
> **Status:** Draft for review. The generic core is in bbsengine6:
> [`bbsengine6/handbook/specs/front-end-seam.md`](../../../bbsengine6/handbook/specs/front-end-seam.md). This file
> holds only casino's per-application sections. Blackjack (section 12) is the first migration. No code
> changes until this spec is approved.
> **Structure:** Part B only. Part A (`ActionResult`, the codes, the events, input, compatibility,
> and verification) is defined in bbsengine6, and each application section here follows its rules.

## 11. Out of scope

- The door-mode versions of any application's domain (for example `blackjack/play.py`, which uses its own
  in-memory `Hand`).
- Changing the client wire protocol.
- Wrapped or multi-line status display in any front end.

## 12. Blackjack (first migration)

**Current state (verified):**

- `services/game.py` defines `GameService` with `start_game`, `place_bet`, `hit`, `stand`,
  `double`, `split`, `surrender`, `can_surrender`, `settle_game`, and `take_settled_round`.
- The only runtime caller of `GameService` is `api/handler.py` (`GameServiceHandler`). It calls
  `hit`, `stand`, `double`, `split`, `surrender`, `settle_game`, and `take_settled_round`.
- `services/round_clock.py` refers to `GameService` only in a comment.
- `blackjack/play.py` and `blackjack/settle.py` do not call `GameService`.
- `services/game.py` calls `io.echo` 41 times across the service package; blackjack's own domain
  code calls it 24 times.

**Domain codes** (added to the enum; the generic set and the rule are in bbsengine6's
`front-end-seam.md`, section 4). Casino's table, bet, and balance codes (`table_not_found`,
`not_at_table`, `invalid_bet`, `insufficient_funds`) are casino's own, defined in `api/messages.py`,
with their wire values unchanged:

| Code | Replaces message |
|---|---|
| `no_active_game` | "No active game" |
| `round_expired` | "The round clock expired" |
| `hand_not_found` | "No hand found" / "Hand not found" |
| `no_bet_found` | "No bet found" |
| `cannot_split` | Split refusals (the reason is in `message`) |
| `cannot_double` | Double refusals |
| `cannot_surrender` | Surrender refusals (the reason is in `message`) |

The refusal `message` text stays as it is today, so a front end that shows `message` looks the same.

**Domain event kinds:** `round_started` (`shoe_cards`, `dealer_up`), `bet_placed` (`amount`),
`card_dealt` (`hand_id`, `card`, `total`), `hand_settled` (`hand_id`, `outcome`, `payout`),
`round_expired` (`table`).

**Requests:**

| Request | Maps to |
|---|---|
| `StartGame(table, game_type)` | `start_game` |
| `PlaceBet(table, moniker, amount)` | `place_bet` |
| `Hit(table, moniker)` | `hit` |
| `Stand(table, moniker)` | `stand` |
| `Double(table, moniker, hand_id)` | `double` |
| `Split(table, moniker, hand_id)` | `split` |
| `Surrender(table, moniker)` | `surrender` |

**Results per method (`data`):**

| Method | `data` |
|---|---|
| `start_game` | `game_id`, `game_type`, `state` |
| `place_bet` | `amount`, `balance` |
| `hit` | `hand_id`, `cards`, `total`, `busted` |
| `stand` | `hand_id`, `total` |
| `double` | `hand_id`, `cards`, `total`, `busted`, `balance` |
| `split` | `hand_ids` |
| `surrender` | `hand_id`, `refund` |
| `can_surrender` | `allowed` (no refusal code; a bool result) |
| `settle_game` | `outcomes` (one entry per hand) |
| `take_settled_round` | `outcomes`, `payouts` |

## 13. Template for another application

To migrate another application's domain (poker, slots, yahtzee, tictactoe), add a section here with these parts, and
change nothing in Part A:

1. **Current state.** The service, its callers, and the `io.echo` count, checked in the code.
2. **Domain codes.** Only refusals the domain makes that the generic table does not cover. Each goes
   into the enum.
3. **Domain event kinds.** Name, when emitted, and payload. No name may match a message kind.
4. **Requests.** One row per request, mapped to a method.
5. **Results per method.** The `data` table.
6. **Migration order.** The methods, and which API handler maps them.

## 14. Open questions

- The TUI's queue drain point is an implementation question for the TUI adapter step, not a
  spec question.
- Whether an event queue is per table or per process. Section 5 orders events per table; the
  queue's scope is decided with the first implementation.
