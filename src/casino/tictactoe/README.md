# Tic-Tac-Toe v1

BED-only tic-tac-toe for the casino. Three modes:

- **Mode 0** — 2 AI, server self-plays to completion; spectators see
  the moves streamed as `tictactoe_state` messages.
- **Mode 1** — 1 human vs AI. Human is X, AI is O. AI replies
  immediately after each human move.
- **Mode 2** — 2 humans on the same `table_moniker`, networked via
  WebSocket with turn-order enforced by `turn_moniker`. Owner is X,
  second joiner is O.

## Bank model

- Player money: `engine.__member.credits`. Debit on bet via
  `dal_bet.place_bet`; credit on settlement via `dal_bet.settle_bet`.
  One `__betlog` row per session.
- Table treasury: `bank.__account` keyed on `table_moniker`, via
  `__bank_table` mapping. Auto-created by
  `services.table.TableService.create_table` with `hidden=True`.
- `__table` row stays `status='open'` across sessions; reused by
  `quick_play` on the next session.
- One `__game` row per session; closed at end of the match (winner
  decided or draw) or cancelled on disconnect.
- `RAKE_PERCENT = 0` in v1; the rake field in the per-turn `__log`
  row is always 0.

## Payout

- **Win (1:1):** winner's bet is doubled (`payout = bet * 2`).
- **Draw (push):** bet is refunded (`payout = bet`).
- **Loss:** no payout (`payout = 0`).

In v1 the bettor is always the X player. Mode 1's X is the human;
mode 2's X is the table owner.

## BED message protocol (hybrid)

Server owns randomness and game state. Client owns choice. All
messages use the existing WebSocket transport.

### Client → Server

- `tictactoe_quick_play` `{mode: int, bet?: int}` — lazily creates a
  hidden tic-tac-toe table owned by the player, opens a `__game`
  row, places the per-session bet (table's `minimumbet`), returns
  initial `tictactoe_state`. For mode 0 the server begins self-play
  immediately. The table is also stored in the session so
  subsequent messages resolve the table_moniker automatically.
- `tictactoe_move` `{cell: int}` — human player places a mark in
  `cell` (0–8). Server applies the move, broadcasts state, then in
  mode 1 the AI replies and the resulting state is broadcast. In
  mode 2 the turn flips to the other human.
- `tictactoe_resign` — forefeit; opponent wins; bettor loses.
- `tictactoe_join` — mode 2 only: second human takes the O seat.

### Server → Client

- `tictactoe_state` — broadcast to `casino:table:{moniker}` after
  every successful state change. Payload:

  ```json
  {
    "type": "tictactoe_state",
    "table_moniker": "ttt-alice",
    "mode": 1,
    "board": [0, 1, 0, 0, 0, 2, 0, 0, 0],
    "to_move": 1,
    "turn_moniker": "alice",
    "winner": null,
    "is_draw": false,
    "is_over": false,
    "last_move": {"cell": 4, "mark": 1, "by": "alice"},
    "moves_played": 1
  }
  ```

- `tictactoe_result` — sent once at end of match. Payload:

  ```json
  {
    "type": "tictactoe_result",
    "table_moniker": "ttt-alice",
    "mode": 1,
    "winner": 1,
    "winner_moniker": "alice",
    "is_draw": false,
    "board": [1, 1, 1, 0, 2, 2, 0, 0, 2],
    "moves_played": 5,
    "payout": 20,
    "new_balance": 120,
    "rake": 0
  }
  ```

- `{"type": "error", "code": "...", "message": "..."}` — for
  `bad_mode`, `not_at_table`, `not_your_turn`, `cell_occupied`,
  `cell_out_of_range`, `game_over`, `not_authenticated`,
  `wrong_mode_for_action`, `table_full`, `not_your_seat`.

## Server-side rules

- `tictactoe_quick_play` mode is **immutable** for the session.
- **Mode 0:** `tictactoe_move` always rejected. Engine self-plays
  perfect vs. perfect (with the default `RANDOMIZE_FIRST_MOVE =
  False`, this always ends in a draw).
- **Mode 1:** human = X, AI = O. `tictactoe_move` triggers an AI
  reply via `lib.best_move` (alpha-beta-pruned perfect play). A
  second player trying to join gets `table_full`.
- **Mode 2:** two humans required; `turn_moniker` alternates by
  mark. `tictactoe_join` takes the O seat if it's free.
- Win detection server-side via `lib.check_winner`. AI uses the
  same function so they never disagree.
- Draw = push: `settle_bet(payout=bet)`. Win = `settle_bet(payout=bet*2)`.
- Each turn writes one `__log` row with `attrs={"move": int, "by":
  str, "moves_played": int}`.
- On game over, sets `__game.status = 'closed'`, sends
  `tictactoe_result` to the player, removes the game from
  `_games`. `__table` stays open.
- Disconnect mid-game: `finalize_on_disconnect` settles the open
  bet as a loss (`payout=0`), sets `__game.status = 'cancelled'`.
  Mode 0 ignores disconnects. Mode 2 picks the leaver as the
  loser.

## File layout

- `lib.py` — pure engine: `Board`, win detection, minimax+αβ AI,
  payout math. No DB, no I/O, no BED.
- `dealer.py` — thin shim around `lib.best_move` for DI in tests.
- `player.py` — input validator for human moves (cell range +
  occupancy).
- `service.py` — `TictactoeService` per-table registry +
  `TictactoeGame` dataclass; handles bank, AI replies, mode
  enforcement, mode-0 self-play, disconnect cleanup.
- `tests/test_tictactoe_lib.py` — 57 unit tests for the pure
  engine.
- `tests/test_tictactoe_service.py` — 38 integration tests with
  mocked DB.

## v1 limitations (out of scope)

- AI difficulty is hardcoded to perfect (`RAKE_PERCENT = 0`).
  `RANDOMIZE_FIRST_MOVE = False` (mode 0 always draws).
- No replay/history viewer.
- No tournament mode.
- No door-mode `play.py` (BED-only).
- Door-mode surface in `client/casino_client.py` is a thin wrapper: `X` for
  `tictactoe_quick_play` (prompts for mode 0/1/2), `V` for
  `tictactoe_move` (prompts for cell 0-8), `N` for
  `tictactoe_join` (mode 2 O-seat), `G` for `tictactoe_resign`.
  The full board is rendered by the BBS client when it receives
  the `tictactoe_state` broadcast.
- No second-human-upgrade from mode 1 to mode 2; the second
  joiner is rejected with `table_full`.
- Misère variant, configurable AI, configurable rake are all
  deferred to v2.
