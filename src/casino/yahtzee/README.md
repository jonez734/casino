# Yahtzee v1

BED-only single-player yahtzee. Replaces the legacy door-mode stub.

## Bank model

- Player money: `engine.__member.credits`. Debit on bet, credit on
  payout, via `dal_bet.place_bet` / `dal_bet.settle_bet`. One
  `__betlog` row per session (single bet at start, settled
  round-by-round).
- Table treasury: `bank.__account` keyed on `table_moniker`, via
  `__bank_table` mapping. Auto-created by
  `services.table.TableService.create_table` with `hidden=True`.
- `__table` row stays `status='open'` across sessions; reused by
  `quick_play` on the next session.
- One `__game` row per session; closed at end of 13th round.
- `RAKE_PERCENT = 0` in v1; rake code is in `lib.py` but
  commented out, so `net_payout(score) == score`. The rake field
  in the per-turn `__log` row is always 0.

## BED message protocol (hybrid)

Server owns randomness; client owns choices. All messages use the
existing WebSocket transport.

### Client → Server

- `yahtzee_quick_play` — lazily creates a hidden yahtzee table
  owned by the player, opens a `__game` row, places the per-session
  bet (table's `minimumbet`), returns initial `yahtzee_state`. The
  table is also stored in the session so subsequent messages
  resolve the table_moniker automatically.
- `yahtzee_roll` — server rolls the 5 dice; `rolls_left` goes 2→1.
- `yahtzee_reroll` `{locks: [int, ...]}` — server rolls the
  unlocked dice, preserves the locked indices' values;
  `rolls_left` decrements. Allowed when `rolls_left > 0`.
- `yahtzee_score` `{category: str}` — server scores the current
  dice into the named category, credits the player via
  `dal_bet.settle_bet`, writes one `__log` row, advances the
  round, resets `rolls_left = 2`. If the round was the 13th,
  closes the `__game` and returns `yahtzee_result` instead.
  When the 13th round is scored, the server also merges
  `{outcome, bet_amount, net}` into the `__game` row's
  `attrs` JSONB (`outcome = "win" if net > 0 else "loss"`),
  via `dal.game.update_game_attrs` (sync + aiosql) — this is
  what feeds the per-table `get_table_stats` aggregate when
  `Moniker.create_table` short-circuits on a duplicate moniker.
  See `casino.SPEC.md` §9.

### Server → Client

- `yahtzee_state` — broadcast to `casino:table:{moniker}` after
  every successful state change. Payload:

  ```json
  {
    "type": "yahtzee_state",
    "table_moniker": "yahtzee-alice",
    "round": 0,
    "dice": [0, 0, 0, 0, 0],
    "locked": [false, false, false, false, false],
    "rolls_left": 2,
    "scorecard": {
      "ones": null, "twos": null, "threes": null,
      "fours": null, "fives": null, "sixes": null,
      "three_of_a_kind": null, "four_of_a_kind": null,
      "full_house": null, "small_straight": null,
      "large_straight": null, "yahtzee": null, "chance": null
    },
    "running_total": 0,
    "last_score": 0,
    "is_over": false
  }
  ```

- `yahtzee_result` — sent once at end of 13th round. Payload:

  ```json
  {
    "type": "yahtzee_result",
    "table_moniker": "yahtzee-alice",
    "final_scorecard": {"ones": 3, "twos": 6, ...},
    "upper_total": 30,
    "lower_total": 35,
    "grand_total": 65,
    "rake_total": 0,
    "new_balance": 0
  }
  ```

- `{"type": "error", "code": "...", "message": "..."}` — for
  bad_category, category_used, no_active_game, not_at_table,
  not_authenticated, wrong_player, no_rolls_left,
  not_at_start_of_round, bad_locks.

## Server-side rules

- `yahtzee_roll` allowed only at start of a round
  (`rolls_left == 2`).
- `yahtzee_reroll` allowed when `rolls_left > 0`. Locks are a list
  of indices in `[0, 4]`.
- `yahtzee_score` allowed any time the round is active. Validates
  category is one of the 13 categories and is currently
  `None` in the scorecard. Player may score early (before
  exhausting rolls).
- Each successful state change publishes `yahtzee_state` to
  `casino:table:{table_moniker}` so spectators see the dice.
- On `yahtzee_score` that completes the game, sets
  `__game.status = 'closed'`, sends `yahtzee_result` to the
  player, removes the game from `_games`. `__table` stays open.
- Disconnect mid-game: `finalize_on_disconnect` settles the open
  bet as a loss (payout=0), sets `__game.status = 'cancelled'`.
  Hooked into `MessageRouter.unregister_session`.

## v1 limitations (out of scope)

- `games/config.py` registry + `YahtzeeConfig`. Hardcoded
  `RAKE_PERCENT=0`, `MIN_BET=10`, `MAX_BET=1000` in `lib.py`.
- Scorecard persistence (in-memory only; final scorecard in
  `__log.attrs` of the closing log row + the `yahtzee_result`
  payload).
- Player stats (no `casino.__player.stats` keys added).
- Upper-section bonus, yahtzee bonus, joker rule.
- Multiplayer (the bank/scoring logic assumes the player is the
  table owner).
- `cmd_yahtzee_quick_play()` helper in `client/casino_client.py`
  for the BBS-side client (a future commit can wrap the BED
  messages so the `Y` door-mode shortcut can also drive the
  WebSocket protocol end-to-end).

## Door-mode parity

The `Y` menu shortcut in `casino.main` routes to
`casino.commands.yahtzee.lib.play`, which dispatches via
`bbsengine6.module.run` to `casino.yahtzee.game`. The game module
sets up a `YahtzeeDealer` + `YahtzeePlayer` and runs the local
door-mode play loop in `casino.yahtzee.play` (mirrors
`casino.slots.play` and `casino.blackjack.play`).

Two prompts are wired with `KEY_HELP` / `KEY_F1` redraw via
`io.inputchoice(help=...)`:

- **Action prompt** — `[R]oll` / `[L]ock` / `[S]core` / `[Q]uit`.
  Help heading is `play yahtzee`.
- **Score-category prompt** — picks one of the 13 categories.
  Help heading is `score category`.

Both help callbacks call `bbsengine6.util.heading` exactly once
per F1 press, matching the spec. The existing BED-side flow
(`yahtzee_quick_play` / `yahtzee_roll` / `yahtzee_reroll` /
`yahtzee_score` over WebSocket) is unchanged and remains the
recommended path for table.join / table.create users.
