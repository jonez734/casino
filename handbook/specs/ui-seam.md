# casino — UI seam specification (blackjack)

> **Last updated:** 2026-11-09.
> **Status:** Draft for review. Section 5 and 5a (events, bottom bar) and the package
> name are settled. No code changes until this spec is approved.
> **Scope:** blackjack only. `GameService` in `services/game.py`, its blackjack methods, and
> the events a blackjack round produces.

## 1. Purpose

Casino needs more than one user interface: the TUI today, Tk first, then GTK and Qt. The game
and service code must not decide how a result is shown or how input is read. This spec defines
the seam between the game and any UI:

- Game code returns a typed **result** and emits typed **events**. It never calls `io.echo` or
  `io.input*`.
- A UI reads the player's input and sends typed **requests** to the game. It never reads game
  state except through results and events.
- Each UI consumes the same results and events on its own event loop.

## 2. Current state (verified)

- `services/game.py` defines one class, `GameService`, with the blackjack methods
  `start_game`, `place_bet`, `hit`, `stand`, `double`, `split`, `surrender`, `can_surrender`,
  `settle_game`, and `take_settled_round`.
- Every blackjack method returns a plain `dict[str, Any]`. Refusals are
  `{"success": False, "message": "..."}` with no code. Successes are `{"success": True, ...}`.
- The only runtime caller of `GameService` is `api/handler.py` (`GameServiceHandler`, around
  line 1041). It calls `hit`, `stand`, `double`, `split`, `surrender`, `settle_game`, and
  `take_settled_round`, and returns the dicts to clients.
- `services/round_clock.py` refers to `GameService` only in a comment. It is not a caller.
- `blackjack/play.py` and `blackjack/settle.py` do not call `GameService`. The door-mode
  blackjack uses its own in-memory `Hand`. That path is out of scope for this spec.
- `services/game.py` calls `io.echo` 41 times across the service package; blackjack's own game
  code calls it 24 times. These calls mix logs, status text and refusal messages.

## 3. Result type

```python
@dataclass(frozen=True)
class ActionResult:
    ok: bool                      # True when the action happened
    code: str                     # "ok" on success; otherwise a code from section 4
    message: str = ""             # display text only; never branched on
    data: Mapping[str, Any] = {}  # typed payload for the action (see section 6)
```

- `ok` and `code` are the contract. Logic branches on `code`, never on `message`.
- `message` is for display. A UI may translate it by `code`.
- Every blackjack method returns `ActionResult`. The method's own payload goes in `data`.

## 4. Result codes

Codes are defined once, in `api/_auth.py` and `api/handler.py`. The seam reuses them. The only
new codes are the ones blackjack needs that do not exist yet. A code appears in exactly one
place in the code base.

**Reused (already in use by the API):**

| Code | Meaning |
|---|---|
| `ok` | The action happened |
| `table_not_found` | No table with that moniker |
| `not_at_table` | The member is not seated at the table |
| `invalid_bet` | The bet is not a valid amount |
| `bet_below_min` | Bet is under the table minimum |
| `bet_above_max` | Bet is over the table maximum |
| `forbidden` | Operation not permitted |
| `service_error` | Unexpected failure inside the service |

**New (blackjack only, added once to the API vocabulary):**

| Code | Replaces message |
|---|---|
| `no_active_game` | "No active game" |
| `round_expired` | "The round clock expired" |
| `hand_not_found` | "No hand found" / "Hand not found" |
| `no_bet_found` | "No bet found" |
| `cannot_split` | "Can only split with exactly 2 cards", "Cards must have same rank to split", "Maximum splits reached", "Insufficient funds to split" (split refusals; the reason is in `message`) |
| `cannot_double` | Double refusals |
| `cannot_surrender` | "Surrender not allowed at this table", "Can only surrender with exactly 2 cards", "Cannot surrender after hitting" |
| `insufficient_funds` | "Insufficient funds" (any blackjack action that needs funds) |

The refusal `message` text stays as it is today, so a UI that shows `message` looks the same.
A UI that branches shows the code's meaning.

## 5. Events

Blackjack emits events to a queue. The queue is the only channel for round progress.

```python
@dataclass(frozen=True)
class Event:
    kind: str            # from the table below
    table: str           # table moniker
    moniker: str | None  # acting or affected member, when there is one
    payload: Mapping[str, Any]
```

| Kind | Emitted when | Payload |
|---|---|---|
| `round_started` | A round begins | `shoe_cards`, `dealer_up` |
| `bet_placed` | A bet is accepted | `amount` |
| `card_dealt` | A card is drawn to a hand | `hand_id`, `card`, `total` |
| `hand_settled` | A hand is settled | `hand_id`, `outcome`, `payout` |
| `round_expired` | The round clock ends the round | `table` |
| `debug` | A debug message, when the member's debug setting is on | `text`, `source` |
| `info` | An informational message | `text` |
| `ok` | A confirmed success message | `text` |
| `warning` | A non-fatal problem the member should see | `code`, `text` |
| `error` | An action is refused, when the refusal is worth showing unprompted | `code`, `text` |
| `fragment` | A bottom-bar fragment's value changed (see section 5a) | `name`, `value`, `level` |

- Message kinds (`debug`, `info`, `ok`, `warning`, `error`) match the echo levels, so a
  message's level means the same on the echo path and the event path. `warn` is not used;
  `warning` is the only spelling.
- `debug` events are emitted only when the member's debug setting is on. The queue is quiet
  by default. Each UI filters on its own debug setting.
- Refusals are the `error` message kind plus the result `code` (section 4). The code is never
  duplicated in a second vocabulary.
- Events are ordered per table. A UI that drains the queue sees them in the order they
  happened.
- Logging (`logging`) is the file log only. The event queue is the UI channel; a GUI receives
  debug and info text through it, not through the log.

### 5a. Bottom bar as events

The bottom bar is built from named fragments (`register_bottombar_fragment`). A fragment's
value is game or member state. When that value changes, the game emits a `fragment` event, so
a GUI and the TUI show the same values.

- `name` is the fragment's registered name (for example `balance`, `table`, `moniker`).
- `value` is the fragment's current value as data, not formatted text.
- `level` is the echo level the fragment uses, so a UI can colour it the same way as a message.
- A fragment event is emitted on change only, not on every redraw.
- The TUI renders the bar from the same values. Its drawing is a UI concern and is not part
  of this seam.
- **Open question:** the queue's thread model. How the TUI's event loop and the bottom bar
  share output today is not settled. The queue will be drained by each UI on its own loop
  (Tk and Qt run their own loops), but the exact drain point for the TUI is to be decided
  when the TUI adapter is written.

## 6. Results per method

Each method's `data` payload is fixed by this table:

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

## 7. Input

A UI sends a typed request to the game. The game never prompts.

| Request | Maps to |
|---|---|
| `StartGame(table, game_type)` | `start_game` |
| `PlaceBet(table, moniker, amount)` | `place_bet` |
| `Hit(table, moniker)` | `hit` |
| `Stand(table, moniker)` | `stand` |
| `Double(table, moniker, hand_id)` | `double` |
| `Split(table, moniker, hand_id)` | `split` |
| `Surrender(table, moniker)` | `surrender` |

Prompts, menus, and validation messages belong to the UI.

## 8. Compatibility

- **The API wire shape does not change in the first step.** `api/handler.py` maps each
  `ActionResult` back to the dict the client receives today. `{"success": ..., "message": ...}`
  and the existing extra fields stay as they are.
- The mapping lives in one function in `api/handler.py`, so it is removed when clients move to
  `ActionResult` directly.
- The TUI (`commands/`, `client/`) keeps printing the same text. Its adapter prints the events
  it used to print.

## 9. Package and file layout

- New package: `casino/api/ui/`, the UI seam under the existing `api/` package. It holds
  `results.py` (`ActionResult`) and `events.py` (`Event` and the queue).
- `services/game.py` returns `ActionResult` for the blackjack methods.
- `api/handler.py` maps results back to the wire dict (section 8).
- `SPEC.md` section 3 (layered package layout) is updated in the same change to list
  `api/ui/` and to point to this spec. This is a required step, not an afterthought.

## 10. Verification

- The blackjack tests in `tests/` run before and after each method is migrated. They must pass
  unchanged, except where a test asserts a refusal `message` that is deliberately kept.
- Tests for `api/ui/results.py` and `api/ui/events.py`: codes are from the section 4 table; the
  queue preserves per-table order; `ActionResult` is immutable; message kinds are only
  `debug`, `info`, `ok`, `warning`, `error`; `debug` events are not queued when debug is off.
- A migration test per method: the result's `ok`, `code`, and `data` match section 6, and the
  API's wire dict is unchanged.

## 11. Out of scope

- The door-mode blackjack in `blackjack/play.py` (its own in-memory `Hand`).
- The other games (`poker`, `slots`, `yahtzee`, `tictactoe`). They follow after blackjack is
  reviewed against a real migration.
- Changing the client wire protocol.
- Wrapped or multi-line status display in any UI.

## 12. Open questions

None. The package is `api/ui/` (section 9). The TUI's queue drain point is an implementation
question for the TUI adapter step, not a spec question.
