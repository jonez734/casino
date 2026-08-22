# Casino - Not Implemented Features

## Refactor casino menu registrations onto `bbsengine6.menu_next`

The hard-coded 19-entry tuple in `casino/main.py` and the 15-entry
tuple in `casino/client/menu.py` move to per-game `menu()` methods
on each bbsengine6 module. The menu registry walks the module list
at render time. The parallel `menu_next.register_menu_options(
name, ...)` API and the "registrar name" concept go away. The
legacy `bbsengine6.casino` authorization stub is already dropped
in this branch.

Module-based design: each game's `__init__.py` declares
`def menu(args, **kw) -> tuple[MenuOption, ...]`, returns the
launcher + game-specific actions, and `init()` registers the
module via `register_module(apis={"menu": menu})`. The shared
Bet lives in `casino.commands.game.menu()`; per-game actions use
`casino.games.action_menu_option(GameAction.X, GameType.Y)`.
The visibility filter (`requires_seated`, `allowed_game_types`,
`hide_if_seated_type`, `requires_connected`) is unchanged. Sort
order is alphabetical-by-module-name; letter collisions are
resolved at render time by `visible_options()`.

- [ ] `bbsengine6/py/src/bbsengine6/menu_next/registry.py` --
       rewrite `registered_options(name=None, args=None, **kw)`
       to walk `bbsengine6.module.get_all_modules()`, call each
       module's `menu` api, and return the union sorted by
       module name. Drop `register_menu_options()` and the
       private `_OPTIONS` list. `clear_registry()` unregisters
       every module that exposes a `menu` api (test-only).
- [ ] `bbsengine6/py/src/bbsengine6/menu_next/__init__.py` and
       `bbsengine6/py/src/bbsengine6/__init__.py` -- drop the
       `register_menu_options` re-export from both.
- [ ] `bbsengine6/py/tests/test_menu_next_registry.py` --
       rewrite for the module-based shape. Tests register a
       module via `register_module(name=..., apis={"menu":
       static_fn})`, then call `registered_options()` and
       assert the union / per-module filter / unknown-name
       empty / thread-safety smoke. Autouse fixture calls
       `clear_registry()` after each test.
- [ ] `bbsengine6/py/tests/test_menu_next_visibility.py` --
       no change; `visible_options` is unaffected.
- [ ] `casino/src/casino/__init__.py` -- replace the inline
       `menu_next.register_menu_options("casino.lib", ...)`
       call (staged in this branch) with a
       `def menu(args, **kw) -> tuple[MenuOption, ...]`
       method that returns the same 11 door-mode core options:
       Connect (`c`), List tables (`l`), Join table (`j`), View
       table (`v`), Watch table (`w`), Unwatch table (`u`),
       Global msg (`g`), Bank (`k`), Disconnect (`x`,
       `requires_connected=True`), Maintenance (`m`), Play
       (`p`, `requires_seated=True`). `init()` registers the
       module with `apis={"menu": menu}`.
- [ ] `casino/src/casino/blackjack/__init__.py` -- add
       `menu()` returning the Blackjack launcher (letter `b`,
       `hide_if_seated_type={"blackjack"}`) plus the four
       seat-gated actions: HIT, STAND, DOUBLE, SPLIT. Use
       `casino.games.action_menu_option(GameAction.X,
       GameType.BLACKJACK)` for each. `init()` registers
       `apis={"menu": menu}`.
- [ ] `casino/src/casino/poker/__init__.py` -- add `menu()`
       returning the Poker launcher (letter `p`,
       `hide_if_seated_type={"poker"}`). No game-specific
       actions in v1; CHECK / CALL / RAISE / FOLD / ALLIN stay
       out of the registry.
- [ ] `casino/src/casino/slots/__init__.py` -- add `menu()`
       returning the Slots launcher (letter `s`,
       `hide_if_seated_type={"slots"}`) plus the seat-gated
       SPIN action.
- [ ] `casino/src/casino/yahtzee/__init__.py` -- add `menu()`
       returning the Yahtzee launcher (letter `y`,
       `hide_if_seated_type={"yahtzee"}`) plus the seat-gated
       ROLL and LOCK actions.
- [ ] `casino/src/casino/commands/game/__init__.py` -- add
       `menu()` returning the shared Bet option (letter `a`,
       `requires_seated=True`,
       `allowed_game_types={"blackjack", "poker"}`). Dispatch
       still goes through `casino.commands.game`; the registry
       just advertises it.
- [ ] `casino/src/casino/commands/tictactoe/` (NEW) -- create
       the shim package, mirroring
       `casino/src/casino/commands/blackjack/`. New
       `__init__.py` registers the module and exposes `menu()`.
       New `lib.py` dispatches to the existing
       `casino.tictactoe` service. `menu()` returns the
       TicTacToe launcher (letter `n`,
       `hide_if_seated_type={"tictactoe"}`) plus the three
       seat-gated actions: MOVE (`m`), JOINT (`j`), RESIGN
       (`g`).
- [ ] `casino/src/casino/client/__init__.py` (NEW) -- promote
       `casino.client` to a registered bbsengine6 module. New
       `__init__.py` exposes `menu()` returning the 15
       WS-client options (word-stem labels like `et`, `it`,
       `tand`, plus Create / Update / Leave, plus the four
       TicTacToe client actions Move / JoinT / Resign / TicTac)
       and an `init()` that registers with
       `apis={"menu": menu}`. WS-client letters deliberately
       differ from the door-mode letters; each consumer filters
       on its own module name via `registered_options(name=
       "casino.client")`.
- [ ] `casino/src/casino/client/menu.py` -- drop the hard-
       coded `_OPTIONS_SPEC` tuple (lines 22-38). Replace with
       `_OPTIONS_SPEC = tuple(menu_next.registered_options(
       "casino.client"))`. Update the import on line 10.
- [ ] `casino/src/casino/main.py` -- drop the 19-entry hard-
       coded `options = (...)` tuple (lines 47-74). Replace
       with `options = tuple(menu_next.registered_options())`.
       Update the import on line 6 to drop `MenuOption,
       visible_options` and just import `menu_next`. Update
       the two `visible_options(...)` call sites (lines 99,
       161) to `menu_next.visible_options(...)`.
- [ ] `casino/src/casino/commands/slots/lib.py:23` -- update
       the `from casino.menu_lib import MenuOption,
       visible_options` import to `from bbsengine6 import
       MenuOption, menu_next`. Update the `visible_options(...)`
       call site to `menu_next.visible_options(...)`.
- [ ] `casino/tests/test_main_menu_visibility.py` -- rewrite.
       The current AST walker that grepped `main.py` for the
       tuple literal goes away. The new test boots the registry
       by calling every game module's `init(args)` (which
       registers the module + menu), then calls
       `menu_next.registered_options()`, and asserts the
       expected set of `(letter, label, module_path, gates)`
       per state.
- [ ] `casino/tests/test_commands.py` -- update
       `TestMainmenuOptions`, `TestMainmenuHelpWiring`,
       `TestMainmenuDuplicateP`, and `TestSlotsMenuOptions`
       to use the registry instead of the hard-coded spec.
- [ ] `casino/tests/test_menu_registration.py` (NEW) -- per-
       game registration contract test. For each game's
       `init(args)`, call
       `menu_next.registered_options("casino.<game>")` and
       assert the expected set of `MenuOption`s (letter, label,
       module_path, visibility gates).
- [ ] `casino/src/casino/menu_lib.py` -- delete once every
       consumer (`main.py`, `client/menu.py`,
       `commands/slots/lib.py`, tests) has migrated off it.
       `MenuOption` and `visible_options` now live in
       `bbsengine6.menu_next`.
- [ ] `casino/handbook/specs/` and `bbsengine6/handbook/` --
       update menu-related docs / specs in both repos:
       describe the module-based registry (each game's
       `__init__.py` declares its own options; the registry
       walks the module list at render time); document the
       `casino.client` WS-client menu module; document the
       new `casino.games` catalog (`GameType.TICTACTOE`,
       `GameAction.MOVE / JOINT / RESIGN`); cross-reference
       the dropped `bbsengine6.casino` stub and note its
       policy now lives at `casino.access`.

## Refactor `CasinoClient` transport onto `BedConnection`

- [ ] `CasinoClient.connect`/`disconnect`/`send`/`receive`/
      `receive_loop` (`casino/src/casino/client/casino_client.py:41-104`)
      reimplement what `BedConnection` already does
      (`bed/src/bed/client/connection.py:58-327`). After the
      `casino-client` → `casino` merge the CLI surface and the
      arg shape are unified (`--bed-host`, `--bed-port`,
      `--bed-path`, `--bed-call-timeout`) but the transport is
      still a fork. Replace it with a `BedConnection` handle
      held on the client, and switch `send` to call the
      `BedMessageClient._request` helper
      (`bed/src/bed/client/messages.py:27-58`) so the
      bearer-token injection and per-op `BedUnavailable`
      translation come from one place. The interactive UI
      loop (`CasinoClient.run` and the `cmd_*` methods),
      the message dispatch (`handle_message`),
      `display_game_state`, and the auth orchestration
      (`cmd_auth` + `casino.auth`) all stay put — they're
      casino-specific.
- [ ] Drop the `casino.client.casino_client` WebSocket
      transport. The `BedMessageClient`-style subclasses
      under `casino/services/bank_client.py` already
      subclass `bed.client.messages.BedMessageClient` —
      this would let `CasinoClient` follow the same pattern
      for its table / game / chat wire calls instead of
      building dicts by hand in `cmd_*`.

## Run `bbsengine6.startup` at casino bring-up

- [ ] Call `bbsengine6.startup.main(...)` as part of casino's
      bring-up so the engine-level stages (`stage_zero`,
      `stage_one`, `bank` — see
      `bbsengine6.startup.lib.BACKEND_STAGE_NAMES` in
      `bbsengine6/py/src/bbsengine6/startup/lib.py:21`) run
      before casino's own `casino.startup.main`. The engine
      stages do the postgres-role / extension / functions
      / engine checks that `casino.startup` does not.
- [ ] In-progress: an uncommitted diff in
      `casino/src/casino/__main__.py` adds a
      `lib.runmodule(args, "bbsengine6.startup")` call before
      `session.start` and bails out with a hard `return False`
      on failure. Promote that diff into a real change:
      confirm the engine stages are idempotent against an
      already-initialized database, and surface their failure
      as a casino bring-up error.
- [ ] Decide whether `casino.startup.main` should still run
      after `bbsengine6.startup` (likely yes — they cover
      disjoint concerns: engine bring-up vs. casino schema /
      class import). Document the ordering in
      `casino/src/casino/__main__.py`.
- [ ] Mirror the wiring into the in-process path: the door
      mode entry point `casino.main.main` at
      `casino/src/casino/main.py:106` already calls
      `lib.runmodule(args, "startup", ...)` for casino's own
      startup; confirm it does **not** also need to call
      `bbsengine6.startup` (current assumption: `__main__`
      only, since door mode is launched from a node that has
      already been brought up).
- [ ] Tests: extend `casino/tests/test_startup.py` (or add
      one) to cover the engine-startup-fails → casino-bails
      path. Use the same `bbsengine6.startup.lib.runmodule`
      patch seam that `bbsengine6`'s own tests use
      (`bbsengine6/py/src/bbsengine6/startup/main.py:26`).
- [ ] Cross-reference: `bed/TODO.md` should link here once
      `bed` adopts the same bring-up ordering.

## `bootstrap_opencode.sql` resets `casino` schema ownership back to `opencode`

- [x] Remove `casino` from the schema-owner loop in
      `casino/src/casino/sql/bootstrap_opencode.sql:60-62` so that
      running the out-of-band opencode bootstrap script does
      not undo `casino.startup.checkcasino`'s reassignment to
      `zoid6`. The loop currently iterates over
      `['bank', 'engine', 'casino']` and unconditionally issues
      `ALTER SCHEMA %I OWNER TO opencode`. The bank/engine
      schemas need to be opencode-owned for the dev-user script
      to work; the casino schema should stay `zoid6`-owned so
      the SECURITY DEFINER helper `manage_schema_priv` can
      GRANT on it.
- [x] Update the docstring at
      `casino/src/casino/sql/bootstrap_opencode.sql:1-16` so the
      "Schema owners, table owners, GRANTs" section reflects the
      change. The follow-up is idempotent on re-run (running
      `casino.startup.main` again would re-fix the ownership),
      but pinning it once at the source avoids the silent
      dependency on re-running casino startup.

**Closed.** Resolved by the `bootstrap_opencode.sql` →
`bootstrap_zoid6.sql` rename: the script now issues
`ALTER SCHEMA ... OWNER TO zoid6` and `GRANT ... TO zoid6`
across `bank`, `engine`, and `casino` (see
`casino/src/casino/sql/bootstrap_zoid6.sql:60-95`). The
`checkcasino` reassignment is no longer undone by an out-of-band
bootstrap run, and `casino.startup.main` no longer needs the
re-run fallback. The `opencode` role is now referenced nowhere
in the casino SQL layer; the test fixtures that mention
`opencode` (e.g. `test_startup_checkcasino.py`) intentionally
simulate a pre-migration prior owner for the BC reassignment
path and stay as-is.

## `casino.lib.runmodule` kwarg: rename `prefix=` to `package=`

`casino/src/casino/lib.py:559` `runmodule()` currently reads
`kwargs.get("prefix", "casino")` and prepends it to `modulename`
before delegating to `bbsengine6.module.runmodule`. The bbsengine6
contract uses `package=`, not `prefix=` (see
`bbsengine6/py/src/bbsengine6/module.py:255-268` and
`module.py:868-874`). The new `casino/__main__.py:19` call
(`lib.runmodule(args, "startup", package="bbsengine6")`) is
silently mis-routed: `kwargs.get("prefix", ...)` returns the
default `"casino"` and the call resolves to `casino.startup`
(`casino/src/casino/startup.py`) — a totally different module
that does casino's own schema/class import. Engine bring-up
never runs.

Fix is Option A from the discussion: minimal local rename, keep
the f-string shim, forward `package=` through to
`bbsengine6.module.runmodule`.

- [ ] Rename local kwarg in `casino/src/casino/lib.py:559-563`:
      accept `package=`, default `"casino"`, build
      `f"{package}.{modulename}"` as today, and forward
      `package=` to `bbsengine6.module.runmodule` so the
      bbsengine6 resolver sees the same anchor.
- [ ] Update the one explicit caller that passes the kwarg:
      `casino/src/casino/main.py:192` (`prefix="casino.commands"`
      → `package="casino.commands"`).
- [ ] Verify no other `prefix=` call sites remain in
      `casino/src/` (grep confirmed only the one above).
- [ ] Manual smoke test: `python -m casino` prints
      `bbsengine6 startup` heading and the casino
      schema-import pass still succeeds; an in-process
      `casino.commands.<X>` path (e.g. `table.list`) still
      resolves to `casino.commands.table`.
- [ ] Out of scope: `blackjack/lib.py:23-24` has its own
      `runmodule` shim with an inlined `PACKAGENAME` prefix —
      leave alone.

## BED bearer token

- [x] `--token-file` registered on the merged `casino` CLI's argparse
      (`casino.lib.buildargs` → `casino.auth.buildargs(parser=parser)`).
- [x] `CasinoClient.run()` dispatches to
      `casino.auth._connect_with_token` when `args.token_file` is set;
      falls back to the legacy prompt path otherwise.
- [x] `casino.auth._resolve_token_file(args)` silently clears
      `args.token_file` when the resolved path is empty / missing so
      an operator running `casino` before `bed auth login` still gets
      the prompt.
- [x] `casino.auth._connect_with_token` takes an optional `client=`
      kwarg so the post-auth menu loop can run on the same instance
      (`CasinoClient.run` mutation-in-place path).
- [ ] See `bed/TODO.md` "Bearer token" — adopt `bed.api.auth.AuthService`
      for BED-mode authentication and reconnect more broadly. Casino
      benefits strongly: lobby browsing, spectator mode, multi-table
      clients, bot accounts.

## Casino player lifecycle (lazy, audit-on-create)

- [x] Centralize casino player-row materialization in
      `casino.services.player.ensure_casino_player`. Both the WS-client
      auth path (`PlayerService.authenticate`) and the door-mode facade
      (`lib.CasinoPlayer.__init__`) now call the same helper. The
      door-mode facade sets `audit=True` so `casino --debug` shows who
      was auto-materialized; the WS-client path sets `audit=False` to
      keep the wire clean. 1:1 member-to-player shape is preserved
      (no schema change). See `SPEC.md` §2.1 and `docs/AUTH.md`
      ("Member vs casino player") for the rationale.
- [ ] Optional follow-up: an explicit `casino init <moniker>` command
      for sysops who want finer-grained control over who gets a casino
      player row. Not in v1 — the audit echo is enough for now.
- [ ] Optional follow-up: re-introduce an async DAL for player reads
      (the previous `dal/aiosql/player.py` was deleted in this change
      because it was schema-drifted and unused). Only worth doing if
      a real async caller materializes.

## Adopt `bed.client` for WebSocket transport

- [ ] See `bed/src/bed/client/` (new subpackage) and the plan discussed
      in the empyre refactor: `BedConnection`, `BedUnavailable`,
      `probe_bed`, `get_bed_connection`, `reset_bed_connection` are now
      importable from `bed.client`. Empyre's `empyre.bed_client` is a
      re-export shim.
- [ ] Replace the raw `websockets.connect` / `self.ws.send(json.dumps(...))`
      / `self.ws.recv()` calls in `casino/src/casino/client/casino_client.py`
      (`CasinoClient.__init__/connect/send/receive`, lines 23-83) with
      a `bed.client.BedConnection` instance. `connect()` should call
      `probe_bed()` instead of opening the socket eagerly; the actual
      WebSocket is opened lazily on the first `send`, matching empyre.
- [ ] Add `BedConnection.recv()` to `bed/src/bed/client/connection.py`
      (request-id correlation in `send` is unaffected; `recv()` is a
      plain `await ws.recv()` for server-pushed messages like chat and
      `game_state`). Use it from `CasinoClient.receive_loop`.
- [ ] Add `casino/src/casino/services/bank_client.py` with a
      `BedBankClient` that **subclasses
      `bed.client.messages.BedMessageClient`**. Methods take
      `table_moniker` rather than `moniker`; each method translates
      table→owner-moniker and calls `self._request(...)` once. Use
      `not_found=` / `default=` from the
      `BedMessageClient._request` contract (see
      `bed/TODO.md` "`bed.client.messages` — shared base for
      per-project message-family clients") for soft-404 semantics
      where appropriate. This is **not** the same class as
      `bed.client.bank.BedBankClient` — different wire shape, same
      base. Wire `casino.services.bank.BankService` to choose
      between bed and direct DB based on `args.bed_reachable`,
      mirroring `empyre.services.player.PlayerService`. Add a
      `CasinoBankUnavailable` exception parallel to
      `empyre.services.player.PlayerServiceUnavailable`.
- [ ] Out of scope for this pass: `record_win` / `record_loss` /
      `approve_transfer` / `reject_transfer` / `list_pending_transfers`
      in `casino.services.bank.BankService` stay on direct DB until
      matching bed wire messages exist.
- [ ] Test files that use raw `websockets.connect` directly
      (`casino/src/casino/tests/test_*.py`) are intentionally left alone
      — they exercise the wire protocol, not the client wrapper. Add
      `casino/tests/test_client_transport.py` separately.

## BED `Sink` integration with `bbsengine6.io` (cross-project)

- [ ] See `bbsengine6/TODO.md` "`bbsengine6.io` sink infrastructure
  for thin-client BED conversion" (Phases 0–5) — the
  `bbsengine6.io.sink.Sink` protocol, `set_io_sink` /
  `reset_io_sink` contextvar API, `bbsengine6.io.echo_render` and
  `mci.parse` / `mci.render` public functions, and the
  `MessageRouter` / `MessageRouterMixin` in
  `bbsengine6/net/router.py`.
- [ ] See `bed/TODO.md` "BED `Sink` integration with
  `bbsengine6.io`" — the `BEDSink` (per-connection adapter in
  `bed/sinks/bed_sink.py`) and the `on_connect_hook` installation
  point on the `WebSocketServer`.
- [ ] **No code change required for the casino `MessageRouter` in
  v1.** The casino can opt into `MessageRouterMixin` later (a
  one-line change to its class declaration:
  `class MessageRouter(MessageRouterMixin):`) to gain the session
  API. v1 ships without the mixin; the BED sink infrastructure
  works against the bare `casino.api.handler.MessageRouter` (the
  pending-request futures and session dict are managed by the
  `BEDSink` and the `IOServiceHandler`, not by the router itself).
- [ ] **Backward compat**: door mode (no `BEDSink` installed) uses
  the default `DefaultSink` behavior, which is the current
  `bbsengine6.io` behavior byte-for-byte. The
  `bbsengine6/tests/test_io_backward_compat.py` suite passes for
  the casino door-mode pytest corpus.

## BED `menu` message type (casino is the primary driver)

See `bed/TODO.md` "`menu` — single-pick option list, server-side hotkeys" for
the full wire shape, semantics, and validation rules. The casino is the
primary driver: every game menu in the casino today is an
`bbsengine6.io.inputchoice` call with a hard-coded list of hotkeys. The
`menu` message type replaces that with a single BED request/reply envelope
that is consumable by any BED client (TUI, headless, web, bot).

### Cross-reference to other BED message types

The `menu` envelope is a 1:1 projection of `bbsengine6.io.inputchoice()`'s
positional and unconditional kwargs (`prompt`, `options`, `default`,
`noneok`, `rewriteprompt`, `timeout`). Two related message types live
elsewhere in `bed/TODO.md`:

- **`help` / `help_result` / `help_error`** (F1, per-menu): the call site's
  `help=<string or callable>` kwarg is stashed server-side and served
  on demand when the user presses `KEY_F1`. The menu envelope does NOT
  carry help text. See `bed/TODO.md` "Help on demand (F1)".
- **`key_f2` / `key_f2_result` / `key_f2_empty` / `key_f2_error`**
  (F2, session-level): lists new messages from the user's subscribed
  channels. NOT a per-menu help callback; not bound to any `menu`
  `request_id`. Casino's `key_f2` adoption (lobby announcements, open
  tables, tournament invites) is a future task; the envelope shape
  is defined in `bed/TODO.md` "`key_f2` — session-level new-messages
  query".

The `inputchoice` `f2_handler` kwarg is **not** projected to the wire
at all (no game in this monorepo passes it).

### Why casino drives this
- Blackjack, Poker, Roulette, and the lobby each have multiple menus that
  are flat option lists with one keystroke per option.
- They do not need paging, cursors, or insert/edit — i.e. they do not
  need the full `listbox` protocol.
- They are user-facing and bot-facing simultaneously: the same `menu`
  envelope must drive a human TUI and a programmatic bot without
  divergence.

### Per-game menu mapping

#### Blackjack
- [ ] Replace the existing hand-action menu in `src/casino/games/blackjack/main.py`
      with a `menu` envelope. The current options:
  - `[H]it` — `hotkey="H"`, `enabled=<can_hit>`
  - `[S]tand` — `hotkey="S"`, `enabled=true`
  - `[D]ouble down` — `hotkey="D"`, `enabled=<can_double>`, `hint` set
        on disabled to "Not enough chips" or "Not available after hit"
  - `[P]plit` — `hotkey="P"`, `enabled=<can_split>`, `hint` set on
        disabled to "Not a pair" or "Not enough chips"
  - `[Q]uit` — `hotkey="Q"`, `style="danger"`
  - `default` = `"S"`, `timeout` = 60s.
- [ ] Insurance menu (when dealer shows Ace) — separate `menu` envelope
      with `[Y]es (insurance)` / `[N]o`.
- [ ] Surrender menu — when the Surrender feature lands (see "Blackjack
      Missing Features" below), a `[Su]rrender` option joins the hand-
      action menu.

#### Poker
- [ ] Replace the betting-round menu in `src/casino/games/poker/main.py`
      with a `menu` envelope. The current options vary by round
      (pre-flop vs post-flop) and bet state:
  - `[F]old` — `hotkey="F"`, `enabled=<can_fold>`
  - `[Ch]eck` — `hotkey="C"`, `enabled=<can_check>`, `hint` on
        disabled = "There's a bet to call"
  - `[Ca]ll` — `hotkey="L"`, `enabled=<can_call>` (uses `L` to avoid
        collision with `[Ch]eck`)
  - `[R]aise` — `hotkey="R"`, `enabled=<can_raise>`
  - `[A]ll-in` — `hotkey="A"`, `enabled=<can_allin>`, `style="warning"`
  - `[Q]uit` — `hotkey="Q"`, `style="danger"`
  - `default` = `"F"` (fold on timeout is the standard tournament
        rule; confirm with game designer).
- [ ] Raise-amount prompt — when `[R]aise` is picked, follow up with
      `inputinteger{min:min_raise, max:max_raise, default:min_raise}`.
      This is a separate message type, not part of the `menu` envelope.

#### Roulette
- [ ] Replace the bet-type menu in `src/casino/games/roulette/main.py`
      with a `menu` envelope:
  - `[I]nside bets` — `hotkey="I"`
  - `[O]utside bets` — `hotkey="O"`
  - `[Sp]ecial bets` — `hotkey="S"`
  - `[Q]uit` — `hotkey="Q"`, `style="danger"`
- [ ] Inside / Outside / Special sub-menus — each is its own `menu`
      envelope with the specific bet options (single number, split,
      street, corner, line for inside; red/black, odd/even, high/low,
      dozens, columns for outside; neighbours, orphans, tiers for
      special).
- [ ] Bet-amount prompt — `inputinteger{min:table_min, max:table_max,
      default:table_min}`.

#### Lobby
- [ ] Replace the lobby menu in `src/casino/lobby/main.py` with a `menu`
      envelope:
  - `[J]oin table` — `hotkey="J"`
  - `[S]pectate table` — `hotkey="S"`
  - `[C]reate table` — `hotkey="C"`, `enabled=<is_sysop>`
  - `[L]eave lobby` — `hotkey="L"`, `style="danger"`
- [ ] Table-list picker — for `[J]oin table` and `[S]pectate table`,
      follow up with a `listbox` (not `menu`) so the player can scroll
      through open tables. The `listbox` protocol is owned by empyre's
      plan; casino reuses the same primitive.

#### Account / bank
- [ ] Replace the in-game account menu (chips balance, deposit,
      withdraw, transfer, history) with a `menu` envelope:
  - `[B]alance` — `hotkey="B"`
  - `[D]eposit` — `hotkey="D"`
  - `[W]ithdraw` — `hotkey="W"`
  - `[T]ransfer` — `hotkey="T"`
  - `[H]istory` — `hotkey="H"`
  - `[Q]uit` — `hotkey="Q"`, `style="danger"`
- [ ] All amount inputs are `inputinteger`; all recipient inputs for
      transfer are `inputstring` (followed by an `inputinteger` for
      amount).

### Non-menu consumers (bots, lobby clients)
- [ ] The casino `MessageRouter` (`src/casino/api/handler.py`) exposes a
      `casino_menu` service for non-menu consumers (bots, lobby
      clients) that wraps the same envelope. This lets a bot driver
      send `{"type":"casino_menu", "table_id":"…", "action":"hit"}` and
      receive the rendered menu envelope back, without going through
      the TUI / thin-client IO path.
- [ ] The `casino_menu` service is **read-only** for bots — a bot can
      observe the current pending menu (and any in-flight reply) but
      cannot inject a `menu_reply` on behalf of the human player.
      Bot-driven play is handled by a separate `casino_bot_action`
      service (already in the casino TODO backlog).

### Migration plan
- [ ] Add `src/casino/api/menu_adapter.py` that converts a casino
      in-process `Menu` dataclass (the existing game-internal menu
      representation) into a `menu` envelope and back. This adapter is
      the single conversion point; the game modules do not need to
      change their internal logic.
- [ ] In `src/casino/api/handler.py`, register a `CasinoMenuService`
      that owns the per-session pending `menu` future (mirrors
      `bed.api.session`'s pending-request table) and dispatches the
      `menu` / `menu_reply` / `menu_timeout` / `menu_cancel` envelopes.
- [ ] For each game (Blackjack, Poker, Roulette, Lobby, Account),
      replace the `bbsengine6.io.inputchoice(...)` call with a
      `casino_menu_adapter.send(session, menu)` call. The adapter
      blocks (or, in async, awaits) until the `menu_reply` arrives.
- [ ] In `--thick` door mode, the adapter renders the same menu using
      `bbsengine6.io.inputchoice` so the door-mode UX is unchanged.
      This is the regression guard.

### Tests
- [ ] `tests/test_menu_blackjack.py` — full hand flow: deal → `menu`
      with `[H]it` enabled → pick `H` → deal → `menu` with `[S]tand`
      enabled and `[D]ouble down` disabled (after a hit) → pick `S`
      → resolve. Asserts the `menu` envelope matches the wire shape
      and the `menu_reply` round-trips.
- [ ] `tests/test_menu_poker.py` — pre-flop vs post-flop menus
      (`[Ch]eck` enabled vs disabled), `[A]ll-in` `style="warning"`.
- [ ] `tests/test_menu_roulette.py` — top-level + sub-menus (inside,
      outside, special), bet-amount `inputinteger` follow-up.
- [ ] `tests/test_menu_lobby.py` — `[C]reate table` disabled for
      non-sysop, table-list `listbox` follow-up.
- [ ] `tests/test_menu_disabled_option.py` — disabled hotkey is
      rejected by the client and the server never sees it; server-
      side `enabled` flag is the source of truth.
- [ ] `tests/test_menu_timeout.py` — server sets `timeout=2`,
      `default="S"`; client never replies; server sends
      `menu_timeout{default_hotkey:"S"}` and proceeds as if the
      player picked `S`.
- [ ] `tests/test_menu_cancel.py` — server sends `menu_cancel{
      reason:"round_ended"}` mid-hand; client drops; late
      `menu_reply` is a no-op on the server.
- [ ] `tests/test_menu_duplicate_hotkey.py` — server tries to send
      a menu with two `H` options; the `MenuService` raises
      `DuplicateHotkeyError` and surfaces as
      `error{code:"menu_duplicate_hotkey"}` to the client.
- [ ] `tests/test_menu_esc_cancel.py` — `[Q]uit` is in the options;
      `ESC` produces `menu_reply{cancelled:true}` with
      `hotkey="Q"` (i.e. the cancel hotkey is reported as the pick).
- [ ] `tests/test_menu_door_mode_regression.py` — `--thick` mode
      still uses `bbsengine6.io.inputchoice`; the same blackjack
      hand produces identical ANSI output as the pre-conversion
      baseline.

### Definition of done
- [ ] All ten test files above pass.
- [ ] The legacy door-mode casino pytest suite still passes with the
      `MenuService` installed in thick mode.
- [ ] A scripted `headless` casino bot can connect, `auth`, join
      a blackjack table, receive a `menu` envelope, send
      `menu_reply{hotkey:"H"}`, and observe the next `menu` (or the
      hand resolution `echo`) — all without a real human in the
      loop.
- [ ] A `tui` casino client can connect, `auth`, render a blackjack
      hand's `menu`, accept a keystroke (`H`), send `menu_reply{
      hotkey:"H"}`, and render the next frame.

## Blackjack Missing Features

- [X] 1. **Surrender** - Player can surrender mid-hand, forfeit 50% of bet
- [X] 2. **5-card Charlie** - Automatic win with 5 cards without busting
- [X] 3. **Dealer soft 17 rule** - Configurable table rule: dealer hits or stands on soft 17 (A+6)
- [X] 4. **Face-down dealer card** - Standard blackjack: show 1 card face-up, 1 face-down
- [X] 5. **Statistics tracking** - Persistent win/loss/push/blackjack/net stats per player (JSONB column, extensible)
- [ ] 6. **Table access control** - Role-based access for who can play at which tables
- [ ] 7. **Card image resizing** - PIL-based PNG resizing for Tkinter card display
- [ ] 14. **AI bot players** - Allow table owner/sysop to fill empty seats with AI-controlled players

## Integration Test Issues

- [X] Hole card: not hiding properly in integration tests (needs debug)
- [ ] **Slots integration test fixtures violate `chk_member_moniker_format`**
  (test_slots_integration.py:406-408, 426, 454, 459, 511, 522, 537, 542,
  556, 574, 578, 602, 627, 636, 649, 655, 680, 689, 700, 713, 723, 735,
  746, 757, 778, 794, 805, 813, 820, 827, 835, 845, 850, 860).

  The test class uses monikers like `jam-1`, `jam-2`, `slots-jam-1`,
  `blackjack-jam-1` — all with hyphens. The `engine.__member.moniker`
  column has a `chk_member_moniker_format` check constraint requiring
  `^[a-zA-Z0-9_]+$` (alphanumeric + underscore only, no hyphens), so
  `_ensure_test_user` (test_slots_integration.py:334) raises a
  `psycopg.errors.CheckViolation` before the test even runs.

  Because the tests are decorated
  `@unittest.skipUnless(_db_available(), ...)` and require
  `CASINO_TEST_DB` in the environment, the bug has been silently
  masked. Setting `CASINO_TEST_DB=zoid6test` (against the local
  zoid6test database) exposes 26 failures — all 26 in
  `test_slots_integration.py`, all with the same CheckViolation
  root cause.

  Fix is a one-time fixture rename: replace `jam-1` → `jam_1`,
  `jam-2` → `jam_2`, `slots-jam-1` → `slots_jam_1`,
  `blackjack-jam-1` → `blackjack_jam_1` throughout the file
  (38 references). Verify the assertions on
  `table_moniker` strings still match the production code path
  (slots table monikers are constructed from player monikers in
  the BED message contract).

  Originally added in commit `354aa74` ("Add slots v1.1: single-seater
  enforcement + bed integration tests"). Last touched in the same
  commit — never updated after the moniker format constraint was
  tightened.

## Poker

- [X] **Texas Hold'em** - Implemented with No-Limit, Pot-Limit, Fixed-Limit
- [X] **Omaha** - Implemented with Pot-Limit (must use 2 hole cards)
- [X] **7-Card Stud** - Implemented with Fixed-Limit
- [X] **Hand evaluation** - All rankings from Royal Flush to High Card with tie-breakers
- [X] **Betting actions** - Fold, check, call, bet, raise, all-in
- [X] **PokerService** - Game state machine, showdown, pot calculation
- [X] **Database schema** - Tables for hands, bets, pots, seats, stats
- [X] **Commands** - Full CLI for poker actions
- [X] **Tests** - Unit tests (52) and integration tests (37)
- [X] Fix WebSocket broadcast for spectators - spectators watching tables should receive game_state updates after player actions

  **DONE**: Added `server.publish()` calls to `casino:table:{moniker}` channel in `_handle_game_action` and `_handle_bet` in `api/handler.py`. After each player action (hit, stand, double, split, surrender, bet), game_state is now published to all clients subscribed to the table channel.

## Messaging

- [ ] **Say command with targeting** - Add `say` command for quick messaging:
  - `say @everyone <message>` → sends to global chat (all connected users)
  - `say @all <message>` → sends to global chat (all connected users)
  - `say @table <message>` → sends to current table only
  - `say @currenttable <message>` → sends to current table only
  - Examples: `say @everyone I'm the king of the world!` or `say @table I am psyching you out!`
  - Implementation: Add `say` subcommand in commands/chat/, parse target, route to global or table chat

## Other Games (Not Implemented)

- [ ] 8. Roulette
- [ ] 9. Craps
- [ ] 10. Baccarat
- [ ] 11. Video Poker
- [ ] 12. Keno
- [ ] 13. Bingo

## Implement bbsengine6 Message System

**Status:** Phase 1A-1E complete (depends on bbsengine6 message system phases)

See `bbsengine6/TODO.md` for full specification with phases:
- Phase 1A: Core Channel System ✓
- Phase 1B: Persistence ✓
- Phase 1C: Groups, Blocking, Rate Limiting ✓
- Phase 1D: Multi-Channel Delivery ✓
- Phase 1E: Templating ✓ - Create new test file `test_message_templating.py` (~52 tests)

### Casino-Specific Integration

- **Channel naming:** `casino:table:{moniker}` for table game updates
- **Personal channel:** `member:{moniker}` for direct member-to-member messages

**Integration steps (Phase 1A+1B DONE):**

1. ✓ Add channel subscription message handlers in `api/handler.py`:
   - `subscribe_channel` - subscribe session to a channel
   - `unsubscribe_channel` - unsubscribe from a channel
   - `get_subscriptions` - list current subscriptions

2. ✓ On `join_table`: auto-subscribe to `casino:table:{moniker}`

3. ✓ On `watch_table`: also subscribe to `casino:table:{moniker}` (unifies player/watcher logic)

4. On `leave_table` and `stop_watching`: unsubscribe from table channel

5. On authentication (`auth` message): auto-subscribe to `member:{moniker}` for direct messages

6. ✓ Update `startup.py` to include message.sql

7. On disconnect: unsubscribe from all channels

8. (After Phase 1B) Message system replaces notify - client notification polling uses message tables instead of notify

9. Convert chat commands to use message system:
   - `chat_table` → publish to `casino:table:{moniker}` channel
   - `chat_global` → publish to `system:shout` channel
   - `emote` → publish to table or global channel (same as chat)

**Tests:** 10 integration tests passing

**Channel mapping:**
| Command | Channel |
|---------|---------|
| chat_table | casino:table:{table_moniker} |
| chat_global | system:shout |
| emote (at table) | casino:table:{table_moniker} |
| emote (global) | system:shout |

Note: `system:announcements` is reserved for sysop broadcasts only.

---

## Chat Persistence (Future)

Store chat messages in database for audit and history.

**SQL files in `casino/src/casino/sql/`:**
```
chat_message.sql              -- table: channel, sender_moniker, message, status, timestamp
chat_channel.sql             -- table: channel metadata and ACL
chat_message_view.sql        -- view with local timestamps
```

**Table: `casino.__chat_message`**
```sql
CREATE TABLE casino.__chat_message (
    id SERIAL PRIMARY KEY,
    channel VARCHAR(255) NOT NULL,
    sender_moniker VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'sent',  -- sent, delivered, read, deleted
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chat_message_channel ON casino.__chat_message(channel);
CREATE INDEX idx_chat_message_timestamp ON casino.__chat_message(timestamp);
CREATE INDEX idx_chat_message_status ON casino.__chat_message(status);
-- Grants in same file
```

**Table: `casino.__chat_channel`** (metadata and ACL)
```sql
CREATE TABLE casino.__chat_channel (
    name VARCHAR(255) NOT NULL PRIMARY KEY,
    acl JSONB DEFAULT '{"kind": "public"}'::jsonb,  -- access control
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT now(),
    attrs JSONB DEFAULT '{}'::jsonb  -- extra metadata
);
-- Grants in same file
```

**ACL JSONB structure:**
```json
{
    "kind": "public|private|invite",
    "allowed_roles": ["sysop", "moderator"],
    "allowed_members": ["alice", "bob"],
    "blocked_members": ["spammer"],
    "moderators": ["alice", "bob"],
    "max_history": 1000
}
```
- `kind: public` - anyone can join/read/post
- `kind: private` - only allowed_members can join
- `kind: invite` - moderator invite only
- `moderators` - JSONB array of member monikers who can manage the channel

**View with local timestamps** (follows empyre.player pattern):
```sql
CREATE OR REPLACE VIEW casino.chat_message AS
SELECT 
    c.id,
    c.channel,
    c.sender_moniker,
    c.message,
    c.status,
    timezone(currentmember.tz, c.timestamp) AS local_timestamp,
    c.timestamp AS utc_timestamp
FROM casino.__chat_message c
LEFT OUTER JOIN engine.__member AS currentmember 
    ON (currentmember.loginid = CURRENT_USER);
-- Grants in same file
```

**DAL stubs in `casino/dal/chat.py`:**
- `insert_message(channel, sender_moniker, message)` - store message
- `get_messages(channel, limit=50, offset=0)` - retrieve history
- `get_channel_acl(channel)` - get channel access rules
- `set_channel_acl(channel, acl_json)` - update channel access

**API in `api/handler.py`:**
- `chat_history` message type: `{"type": "chat_history", "channel": "casino:table:blackjack-1", "limit": 50}`

**Integration:**
- In `handle_broadcast()`: before publishing chat to channel, also call `insert_message()`
- Client can request history on channel join

---

### Database Startup Updates

Each table, view, and index in its own SQL file with grants. Follow pattern in `bbsengine6/sql/notify.sql`:

```sql
-- file: chat_message.sql
CREATE TABLE casino.__chat_message (
    id SERIAL PRIMARY KEY,
    channel VARCHAR(255) NOT NULL,
    sender_moniker VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'sent',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_message_channel ON casino.__chat_message(channel);
CREATE INDEX idx_chat_message_timestamp ON casino.__chat_message(timestamp);
CREATE INDEX idx_chat_message_status ON casino.__chat_message(status);

GRANT SELECT ON casino.__chat_message TO web;
GRANT ALL ON casino.__chat_message TO term, sysop;
GRANT ALL ON casino.__chat_message_id_seq TO term, sysop;
```

Update `casino/startup.py`:
- Add each class to `classlist` tuple in dependency order
- Ensure proper import order (table before view)

---

## Casino Message System Phases

The phases here align with bbsengine6 phases:

- **Phase 1A (Core)**: Table channels work immediately
- **Phase 1B (Persistence)**: Chat persistence in casino.__chat_message
- **Phase 1C (Groups/Blocking)**: Channel ACL enforcement
- **Phase 1D (Multi-Channel)**: Email/SMS delivery to members
- **Phase 1E (Templating)**: Message templating

### Tests

Add tests for all casino message system features:

- `test_join_table_auto_subscribe` - player auto-subscribes to table channel
- `test_watch_table_auto_subscribe` - watcher subscribes to table channel
- `test_leave_table_unsubscribe` - player leaves, unsubscribes from table
- `test_stop_watching_unsubscribe` - watcher stops watching
- `test_game_state_via_channel` - game_state published via channel system
- `test_chat_via_channel` - chat messages published via channel
- `test_auth_auto_subscribe_member_channel` - auth subscribes to member:{moniker}
- `test_direct_message_via_member_channel` - member-to-member messaging works
- `test_chat_persistence` - chat messages stored in DB
- `test_chat_history_retrieval` - chat_history message type works
- `test_channel_acl_enforcement` - private/invite channels enforce ACL
- `test_chat_table_via_channel` - chat_table publishes to casino:table channel
- `test_chat_global_via_channel` - chat_global publishes to system:shout
- `test_emote_via_channel` - emote publishes to appropriate channel

---

## Notes

- All core blackjack features (hit, stand, split, double, insurance, push, blackjack 3:2 payout) ARE implemented and tested.

## Known Issues

- ~~**psycopg-pool 3.3.0 incompatibility**: The async database layer (`casino/dal/aiosql/`) is broken due to API changes in psycopg-pool 3.3.0. The `watch_table` feature fails with "object _AsyncGeneratorContextManager can't be used in 'await' expression". **Fix**: Downgrade to psycopg-pool 3.1.0 with `pip install psycopg-pool==3.1.0`~~ - RESOLVED (bbsengine6 now handles both 3.1.x and 3.3.0+ automatically)
- WebSocket server (bed.py), table management, betting, banking, chat, and player/observer modes are working.

## Pending Workstreams

### Workstream 2: Make test_player_observer.py Pass

**Status:** COMPLETED

**Steps:**
1. Fix port mismatch in `src/casino/tests/test_player_observer.py:226`
   - Change: `WebSocketServer(host="127.0.0.1", port=8766)` 
   - To: `WebSocketServer(host="127.0.0.1", port=8765)`
   - Rationale: Test connects to port 8765 but starts server on 8766

2. Run test to verify:
   ```bash
   cd /home/opencode/data/work/casino/src && python casino/tests/test_player_observer.py
   ```

**Expected behavior:**
- Player connects and plays blackjack
- Observer connects and watches table
- Observer receives `game_state` broadcasts after bet, hit, stand actions
- All assertions pass

**Additional fixes required:**
- Fixed `bbsengine6/database.py`: Added `@asynccontextmanager` decorator to `async_connect()` to properly support async context manager protocol
- Fixed `bbsengine6/database.py`: Fixed `get_async_pool()` to not pass `dbname=None` to `make_dsn()` (caused missing database name in DSN)
- Fixed `bbsengine6/database.py`: Fixed `AsyncCursor.fetchone()` and `fetchall()` to properly await async psycopg cursor methods
- Fixed `bbsengine6/database.py`: Fixed `AsyncCursor.__aexit__()` to call `self._cur.close()` instead of non-existent `_curclose()`
- Fixed `bbsengine6/database.py`: Fixed `async_query()` to use `database.query()` for processing SQL templates with `$schema.table` placeholders
- Fixed `casino/services/game.py`: Added `player_hand` and `player_total` fields to `get_game_state()` return value for backward compatibility with tests and `client/casino_client.py`
- Fixed `casino/tests/test_player_observer.py`: Added async pool cache reset in `asyncSetUp()` and `asyncTearDown()` to ensure clean state between tests

---

### Workstream 3: Rename dbname to database for Clarity

**Status:** COMPLETED

**Problem:** Function parameters like `dbname=` are unclear - `database=` is more explicit.

**Solution:** Support both `dbname` and `database` parameters for backward compatibility, but update casino to use the clearer `database=` style.

**Steps:**

1. **Update bbsengine6/database.py** - Accept both parameters:
   - `get_async_pool(args, database=None, dbname=None)` - use whichever is provided
   - `async_connect(..., database=None, dbname=None)` - same
   - `async_query(..., database=None, dbname=None)` - same
   - `getpool(args, **kwargs)` - handle both in kwargs, normalize before `make_dsn()`
   - `make_dsn(args, **kwargs)` - handle both in kwargs

2. **Update casino code to use `database=`**:
   - `casino/main.py`: `database=args.databasename`
   - `casino/__main__.py`: `database=args.databasename`
   - `casino/startup.py`: `database=args.databasename` (2 places)

3. **Backward compatibility preserved**: All existing code using `dbname=` continues to work

---

### Workstream 4: Update bbsengine6 Database Spec

**Status:** Pending

**File:** `bbsengine6/handbook/specs/database.md`

**Steps:**
1. Add psycopg-pool compatibility note to Overview section (after line 5):
   ```markdown
   **psycopg-pool Compatibility:**
   - Sync API: Works with psycopg-pool 3.x (all versions)
   - Async API: Works with both psycopg-pool 3.1.x and 3.3.0+ (auto-detects API changes)
   ```

2. Add new "Async Database Support" section (~110 lines) covering:
   - `get_async_pool()` - Get/create async connection pool
   - `reset_async_pool_cache()` - Reset pool cache for tests
   - `async_connect()` - Async context manager for connections
   - `async_query()` - Async query helper returning list[dict]
   - `AsyncDBConnection` - Async wrapper class
   - `AsyncCursor` - Async cursor wrapper class
   - psycopg-pool version compatibility table

3. Update "Known Issues" to remove incorrect entries (version compat is a feature, not an issue)

## Extended Statistics (Future)

The stats system uses a JSONB column for extensibility. Currently tracked:

**Generic (aggregate across all games):**
- wins, losses, pushes, net

**Game-specific (prefixed with game type):**
- blackjack.blackjacks, blackjack.busts, blackjack.surrenders, blackjack.hands_played

To add more game-specific stats, use the format `game_type.stat_name`:
- `poker.wins`, `slots.hands_played`, etc.

No database migration needed - just add the stat name to ALLOWED_STATS in dal/player.py

---

## Phase 1F: Notify → message_delivery Rename

Update casino to use message_delivery instead of notify.

**Changes:**
- `casino/src/casino/api/handler.py`: Update imports from `bbsengine6.notify` → `bbsengine6.message_delivery`
- `casino/src/casino/services/bank.py`: Update imports
- Test files: Update any notify imports
- Verify backward compat alias works during transition

**Tests needed:**
- Verify backward compat: `from bbsengine6 import notify` still works
- Verify new import: `from bbsengine6 import message_delivery` works
- Verify both point to same implementation
- All existing notify tests continue to pass

---

## Phase 1G: Postoffice Service (IMAP Polling)

Add postoffice service to BED (via casino) that polls IMAP servers for new email and notifies users.

**bed.json** ✓ (casino package data):
```json
{
  "postoffice": {
    "enabled": true,
    "poll_interval": 30,
    "mailboxes": [
      {"user": "alice", "host": "mail.example.com", "port": 993},
      {"user": "bob", "host": "imap.gmail.com", "port": 993}
    ]
  }
}
```

**Config loading order (priority):**
1. Command line / environment variables (highest)
2. Service reads from config file
3. BED loads defaults from bed.json (lowest)

**Implementation:**
- Add `postoffice.py` module in casino (or create separate package)
- Service class with `handle_message()` method
- Mode A: Background asyncio task polls IMAP on interval (if `enabled: true`)
- Mode B: Handles `check_mail` message type for manual requests

**Message routing:**
- Channel: `postoffice:check_mail`
- Notification: Uses `message.send()` with sender, subject, ~500 char preview

**Integration with BED:**
- Add postoffice service to casino's MessageRouter
- Register message types: `check_mail`, etc.
- Start background polling task on router init

**Tests needed:**

| Test File | What it tests |
|-----------|---------------|
| `test_postoffice_service.py` | Service class, handle_message() |
| `test_postoffice_imap_polling.py` | IMAP connection, polling, new email detection |
| `test_postoffice_background_task.py` | Background polling task starts/stops |
| `test_postoffice_manual_check.py` | Manual check via message type |
| `test_postoffice_notification.py` | Notification sent with correct content |
| `test_postoffice_config.py` | Config loading (3 priority levels) |
| `test_postoffice_channel.py` | Sends to `postoffice:check_mail` channel |

**TODO:** Remove these test files - postoffice service now lives in mistermcfeely package, not casino.

**Key test scenarios:**

1. **Background polling (Mode A):**
   - Service starts, creates asyncio task
   - Polls IMAP on interval
   - Detects new email, sends notification
   - Service stops, task cancels

2. **Manual check (Mode B):**
   - Client sends `check_mail` message
   - Service polls IMAP
   - Returns results to client

3. **Config priority:**
   - Env var overrides bed.json
   - Config file overrides bed.json defaults

 4. **Notification content:**
    - Sender extracted correctly
    - Subject extracted correctly
    - Body preview (~500 chars)

---

## TUI: Replace inputchoice() with inputstring()

**Status:** Planned

Replace all `inputchoice()` calls in the TUI client with `inputstring()` to support typing full action names (e.g., "bet" instead of just "b").

### Part 1: Simplify ActionInputHandler

**File:** `casino/src/casino/client/action_input.py`

Remove hotkey concept - shortest-unique-prefix matching already works via prefix matching on action names.

**`resolve_action()` (lines 9-30):** Remove hotkey exact match, keep only prefix matching:
```python
def resolve_action(input_str: str, actions: list[dict]) -> str | None:
    if not input_str:
        return None
    input_lower = input_str.lower()
    matches = [a for a in actions if a["action"].lower().startswith(input_lower)]
    if len(matches) == 0:
        return None
    if len(matches) == 1:
        return matches[0]["action"]
    options = ", ".join([a["action"] for a in matches])
    raise ValueError(f"Which actions? {options}")
```

**`ActionInputHandler.__init__()` (lines 103-109):** Remove hotkey from action_map:
```python
def __init__(self, actions: list[dict]):
    super().__init__()
    self.actions = actions
    self.action_map = {}
    for a in actions:
        self.action_map[a["action"].lower()] = a["action"]
```

**`ActionInputHandler.get_matches()` (lines 115-132):** Remove hotkey check:
```python
def get_matches(self, prefix: str, **kwargs) -> list[str]:
    if not prefix:
        return [a["action"] for a in self.actions]
    prefix_lower = prefix.lower()
    return sorted(set(a["action"] for a in self.actions 
                      if a["action"].lower().startswith(prefix_lower)))
```

### Part 2: Update Menu Locations

Replace each `inputchoice()` call with `inputstring()` + `ActionInputHandler`:

| File | Line | Actions |
|------|------|---------|
| `main.py` | 156 | Dynamic (from options list) |
| `client/casino_client.py` | 249 | blackjack, poker, slots, yahtzee |
| `client/casino_client.py` | 420 | house, player |
| `client/casino_client.py` | 534 | balance, add, withdraw, transfer, pending, history, list, quit |
| `client/casino_client.py` | 574 | tables, create, update, join, leave, bet, hit, stand, msg, bank, quit |
| | | **Also label [K] as [B]ank in main menu prompt** |
| `commands/game/lib.py` | 120 | bet, hit, stand, double, play, split, quit |
| `commands/poker/lib.py` | 254 | check, all, bet, raise, fold, hand, table, list, quit |
| `commands/table/lib.py` | 94 | tables, create, join, leave, update, view, quit |
| `blackjack/play.py` | 96 | hit, stand |
| `commands/chat/lib.py` | 48 | global, table, quit |
| `commands/bank/lib.py` | 122 | balance, add, withdraw, transfer, pending, history, list, quit |
| `commands/admin/lib.py` | 114 | watch, unwatch, kick, quit |

### Example Pattern

```python
from casino.client import ActionInputHandler

handler = ActionInputHandler([
    {"action": "bet", "hotkey": "", "label": "Bet"},
    {"action": "hit", "hotkey": "", "label": "Hit"},
    {"action": "stand", "hotkey": "", "label": "Stand"},
    {"action": "quit", "hotkey": "", "label": "Quit"},
])
cmd = io.inputstring(
    "{var:promptcolor}Command (bet/hit/stand/quit): {var:inputcolor}",
    completer=handler.get_completer()
)
resolved = handler.resolve(cmd)
```

### Behavior

- User can type full name: "bet", "hit", "stand"
- User can type shortest unique prefix: "b" → "bet", "h" → "hit", "s" → "stand"
- Tab completion shows available options
- Ambiguous input (e.g., "b" when both "bet" and "balance" exist) raises error with options

---

## Sanitize create_table Inputs for Game Type

**Status:** Planned

### Problem
- `TableService.create_table()` accepts `game_type` as raw string with no validation
- API handler passes `game_type` directly from message without validation
- Invalid game types could cause errors or unexpected behavior

### Current State
- `GameType` enum in `games/base.py` defines: `blackjack`, `poker`, `slots`, `yahtzee`
- But this is hardcoded - adding new types requires modifying core code
- Poker variants already use a plugin registry pattern with `entry_points`

### Desired Solution
Make game types pluggable (like poker variants), so third-party packages can add new game types without modifying core code.

### Implementation Steps

#### 1. Create GameTypeRegistry in games/base.py
- Mirror the `VariantRegistry` pattern from poker
- Methods:
  - `register(name, game_class)` - register a game type
  - `get(name)` - validate and return game type (raises ValueError if unknown)
  - `list()` - list all registered types
  - `_register_builtins()` - register blackjack, poker, slots, yahtzee
  - `_discover_from_entry_points()` - discover from entry point group `casino.game_types`

#### 2. Keep GameType enum for backwards compatibility
- Existing code like `GameType.BLACKJACK` still works
- Registry internally uses the same values

#### 3. Update TableService.create_table()
- Call `GameTypeRegistry.get(game_type)` to validate
- Return error dict if validation fails (consistent with PokerService)
- Normalize input (lowercase, strip whitespace)

#### 4. Add helper functions
- `list_game_types()` → returns list of all registered types
- `get_game_type(name)` → returns validated name or raises

#### 5. Add tests
- Valid game types accepted
- Invalid game types rejected with clear error message
- Case insensitivity handling

### Example: Adding a New Game Type

Third-party package would add to their `pyproject.toml`:
```toml
[project.entry-points."casino.game_types"]
mygame = "mypackage.game:MyGame"
```

No core code changes needed - just install the package.

---

## Duplicate-Table Short-Circuit + Per-Table Stats (Completed)

**Status:** COMPLETED (commits `5586723`, `ca01ff7`)

This is the work that landed in `[Unreleased]` of `CHANGELOG.md`:
the `__exists__` sentinel in `dal.table.create_table`, the
`table_exists` envelope with owner-or-sysop gate, the game-type-aware
`get_table_stats` aggregator, and the per-casino nested
configuration block in `bed.json` (surrender_multiplier=0.5 default).
See `SPEC.md` §9 and §10 for the canonical description.

### Bed wiring (deferred)

`MessageRouter._bootstrap_casino_config(args)` auto-discovers the
`casino` section from `args.config_file` so the feature works
without a bed change, but the idiomatic place to wire it is
`bed/main.py` via an `_apply_casino_config(args, cfg)` that mirrors
the existing `_apply_database_config` / `_apply_auth_config` blocks
and forwards `args._casino_config` to `db_args` before constructing
the casino `MessageRouter`. That work is intentionally out of scope
for the casino PR — it should land as a separate bed commit that
also bumps `bed._version.py`.

### Poker stats (deferred)

`get_table_stats` returns `{}` for `game_type="poker"` because
poker runs in-memory in `services.poker.PokerService._tables` and
hand outcomes are awarded via `winner.credits += table.pot` —
nothing is written to `casino.__game` or `casino.__betlog`. A real
poker settlement path that persists per-hand outcomes to
`casino.__game.attrs` (like blackjack / yahtzee / tictactoe now do)
would unlock a non-empty poker stats block. That is its own
workstream.

---

## BED (BBS Engine Daemon) Improvements

**File:** `casino/src/casino/bed.py`

### Missing Features

- [ ] 1. Daemonization - `--foreground` flag exists but daemonization is never implemented
- [X] 3. Configuration file support - Already implemented via bed.json and config.py
- [ ] 4. SIGHUP reload - No way to reload config without full restart
- [ ] 5. Health check endpoint - No /health or /status route
- [ ] 6. TLS/SSL - No WSS (WebSocket Secure) support
- [ ] 7. Connection limits - No max clients or rate limiting
- [X] 8. Authentication - Already implemented via SessionService/PlayerService
- [X] 9. Auto-restart - No watchdog/retry on crash
- [ ] 10. Graceful shutdown timeout - Doesn't wait for connections to close
- [ ] 11. Configurable router - Hardcoded to `MessageRouter` class (bbsengine6 has `--router` flag)
- [X] 12. Overall robustness improvements - Make bed more robust
  - [X] SO_REUSEADDR/SO_REUSEPORT socket flag so port is freed immediately on exit
- [X] 13. SIGHUP reload - Reload config without restart
- [X] 14. Auto-restart - Watchdog/retry on crash (--autorestart, --restart-delay, --max-restarts)

---

## Slots (v1)

Minimal, extensible slot machine game. Single payline (center row) in v1; multi-payline,
bonus rounds, jackpots, and themes are explicit v2 extensions.

### RTP Definition

`RTP = E[payout] / bet` over infinite spins at a flat bet of 1, expressed as a
percentage. Default target is 92%, configurable per-table via
`casino.__table.attrs["slots.target_rtp"]`. A sanity bound of `[0.80, 0.99]` is
enforced at table-creation time; the realized RTP is asserted within ±2% over
10k spins in the integration test suite.

### Bank Integration

**Single atomic transaction per spin.** The bet debit, payout credit, spin
audit row, and player-stat updates all commit together or roll back together.
This diverges from blackjack's per-step model (debit on bet, credit on
resolution) because slots has no inter-player settlement window — there is
exactly one outcome per spin, so collapsing to one bank movement is both
simpler and the right accounting model. Disconnect mid-spin is a non-event:
the transaction either commits or doesn't happen, so there is no in-flight
bet to recover.

### Stats (minimal)

Four entries added to `casino.dal.player.ALLOWED_STATS`:

- `slots.spins` — total spins
- `slots.wins` — spins where `payout > 0`
- `slots.net` — `sum(payout) - sum(bet)`, signed integer (follows existing
  `net` convention)
- `slots.biggest_win` — max single-spin `payout`. Tracked via a new
  `set_max_stat` DAL helper (not additive).

### Rendering

Door mode: 5 reels × 3 rows, box-drawing characters (`┌─┐`, `│`, `└─┘`).
BED clients receive JSON `{reels: [[...], ...], center_row: [...]}` and
render themselves.

### Files to Create

- `casino/src/casino/slots/lib.py` — `Symbol`, `Reel`, `Paytable`, `Win`,
  `SpinResult`, `RNG`, defaults, `render_ascii`
- `casino/src/casino/slots/dealer.py` — `SlotDealer`
- `casino/src/casino/slots/player.py` — `SlotPlayer`
- `casino/src/casino/slots/play.py` — door-mode loop
- `casino/src/casino/slots/game.py` — top-level entry
- `casino/src/casino/services/slots.py` — `SlotService` (atomic transaction)
- `casino/src/casino/dal/slots.py` — spin history, paytable get/set
- `casino/src/casino/sql/slots.sql` — `__slot_spin` table + view + grants
- `casino/src/casino/tests/test_slots_unit.py`
- `casino/src/casino/tests/test_slots_flow.py`
- `casino/src/casino/tests/test_slots_integration.py`

### Files to Edit

- `casino/src/casino/slots/__init__.py` — replace stub, register module
- `casino/src/casino/api/handler.py` — register `SlotServiceHandler`
- `casino/src/casino/startup.py` — add `Slots` to `classlist`
- `casino/src/casino/dal/player.py` — add 4 stat names to `ALLOWED_STATS`,
  add `set_max_stat` helper
- `casino/src/casino/TODO.md` — this section (done in v1 commit)

### Test Coverage (blackjack-depth)

- `test_slots_unit.py` — RNG distribution, paytable evaluation, theoretical
  RTP math, ASCII rendering
- `test_slots_flow.py` — WebSocket spin flow: bet validation, error codes,
  broadcast to spectators, history, single-player enforcement, stats
- `test_slots_integration.py` — door-mode end-to-end, RTP sanity over 10k
  spins, custom paytable via attrs, atomic-transaction rollback on
  simulated failure, bank balance reconciliation

### Extensibility Hooks (designed in, not built)

| Future feature | Hook already in place |
|---|---|
| Multiple paylines | `Paytable.evaluate(center_row)` — v2 adds `active_paylines=[0]` parameter |
| Bonus rounds | `SpinResult.wins` is a list — v2 adds `bonus_state` field |
| Progressive jackpot | `casino.__slot_spin` records every spin — v2 adds `__slot_jackpot_pool` table |
| Provably-fair RNG | `lib.RNG` is a single helper class — swap implementation behind it |
| Per-table paytable | Already in `casino.__table.attrs` JSONB, read by `dal/slots.get_paytable` |
| Symbol themes | `Reel` and `Paytable` constructed from parameters, not hardcoded |

### Out of Scope for v1

- Multiple paylines (3/5/9)
- Bonus rounds (free spins, pick-em)
- Progressive jackpots
- Provably-fair RNG (server seed + client seed + nonce commits)
- Symbol themes beyond defaults
- "Hold" reel feature
- Nudges

### Implementation Order

1. `slots/lib.py`
2. `slots/dealer.py`
3. `sql/slots.sql` + edit `startup.py`
4. `dal/slots.py`
5. Edit `dal/player.py` (stats allowlist + `set_max_stat`)
6. `slots/player.py`
7. `services/slots.py` (with atomic transaction)
8. Edit `api/handler.py` (register handler)
9. `slots/play.py` + `slots/game.py`
10. `slots/__init__.py` (replace stub)
11. Tests: unit → flow → integration
12. `TODO.md` update + lint/typecheck

---

## Generic Per-Game Config

A uniform way for every game (blackjack, poker, slots, yahtzee, future games)
to carry its own typed configuration on a table. The `create_table` and
`update_table` messages accept an optional `config` dict; each game type
defines the schema for its own config via a `GameConfig` subclass registered
in a central registry. The table layer passes the dict through unchanged
and the game-specific service (or the table service at create time) validates
it.

### Wire Shape

```json
{ "type": "create_table",
  "game_type": "slots",
  "min_bet": 1, "max_bet": 100,
  "config": { "target_rtp": 0.92, "reel_set": "default" } }
```

`config` is optional. If omitted, the table is created with the game type's
default `GameConfig` instance.

### Storage

A new `config` JSONB column on `casino.__table`, added via an additive
migration so existing deployments are unaffected:

```sql
alter table casino.__table add column if not exists "config" jsonb default '{}'::jsonb;
create index if not exists idx_table_config_gin on casino.__table using gin (config);
```

The table's `config` column is **always fully populated** after any
successful write — partial / sparse configs are normalized through the
registry at write time, so downstream readers never need to handle missing
keys.

### Update Semantics

`update_table` with `config: {…}` **replaces the whole dict**. Sending
`config: {}` is equivalent to "reset to defaults": the registry parses the
empty dict, fills in every field with the `GameConfig` default, and stores
the fully-populated result. There is no partial-merge / patch API in v1.

### Validation Timing

Validation happens at `create_table` (and again at `update_table`). Bad
config from a sysop surfaces immediately as an error reply, not silently on
the first spin. The registry's `parse()` raises `ConfigError` on schema
violation, which the API handler maps to a `error{code:"invalid_config"}`
reply with the field-level messages.

### Coexistence with `attrs`

`config` and `attrs` are **parallel mechanisms**:

- `config` — structured, validated, per-game-type schema. Owned by each
  game's `GameConfig` subclass.
- `attrs` — freeform JSONB for ad-hoc per-table flags and metadata. Untyped.
  Existing callers continue to use it as today.

`config` does not replace `attrs`. They serve different purposes.

### Architecture

**`casino/games/config.py`**
- `GameConfig(ABC)` — `validate()`, `from_dict()`, `to_dict()`
- `GameTypeConfigRegistry` — `register()`, `get()`, `parse()`. Mirrors the
  `VariantRegistry` pattern from `casino/poker/variant/__init__.py`.
- `ConfigError` — raised on schema violation; carries a list of
  field-level error messages.

**`casino/games/configs/`** — one `GameConfig` subclass per game type:
- `blackjack.py` → `BlackjackConfig`
- `poker.py` → `PokerConfig`
- `slots.py` → `SlotsConfig`
- `yahtzee.py` → `YahtzeeConfig`

Built-in subclasses register themselves on import.

### Per-Game Config Schemas

#### `BlackjackConfig`
| Field | Default | Notes |
|---|---|---|
| `num_decks` | 3 | currently `Shoe(decks=3)` in `blackjack/game.py:29` |
| `dealer_hits_soft_17` | false | TODO.md line 233 — per-table rule, not yet wired through config |
| `allow_surrender` | true | TODO.md line 231 — already in |
| `blackjack_payout` | 1.5 | 3:2; hardcoded in payout logic today |
| `five_card_charlie` | true | TODO.md line 232 — implemented |
| `max_split_hands` | 4 | standard rule; currently unbounded |
| `shoe_penetration` | 0.75 | standard reshuffle point; currently always reshuffles |

`double_after_split` and `allow_insurance` are intentionally **out of v1**:
both are already `true` everywhere, and adding the knob is pure churn. They
land when the per-table override has a real reason to exist.

#### `PokerConfig`
| Field | Default | Notes |
|---|---|---|
| `variant` | `"texas_hold_em"` | hardcoded in `poker/services/poker.py` today |
| `betting_structure` | `"no_limit"` | enum `BettingStructure.NO_LIMIT` |
| `small_blind` | 1 | constructor default |
| `big_blind` | 2 | constructor default |
| `min_buy_in` | 20 | standard default |
| `max_buy_in` | 200 | standard default |
| `min_players` | 2 | per-table default |
| `max_players` | 10 | per-table default |
| `rake_percent` | 0.0 | currently unset; included for future-proofing |
| `rake_cap` | 0 | currently unset; included for future-proofing |

#### `SlotsConfig`
| Field | Default | Notes |
|---|---|---|
| `target_rtp` | 0.92 | see "RTP Definition" above |
| `reel_set` | `"default"` | key into a fixed set of layouts in `lib.py` |
| `paytable_override` | `null` | optional `{symbol: multiplier, …}` dict; embedded (no separate `__slot_paytable` table in v1) |
| `center_row_only` | true | v1 single-payline constraint; flips to `false` when multi-payline lands |

`reels` and `rows` (the 5×3 layout) are **not** in `SlotsConfig` — they
remain constants in `slots/lib.py` (`DEFAULT_REELS`, `DEFAULT_ROWS`).
Changing dimensions at the table level would require revalidating every
paytable entry. Different layouts are a v2+ feature keyed by `reel_set`
(e.g. `"default"`, with `"cleopatra"` stubbed for v2).

`min_bet` and `max_bet` continue to live on the `__table` row, not in
`config`. They apply universally across all game types.

#### `YahtzeeConfig`
| Field | Default | Notes |
|---|---|---|
| `num_dice` | 5 | standard |
| `num_rolls` | 3 | standard |

Minimal in v1. The standard upper-section bonus (63 / 35) is **not** in
config until the bonus is actually wired in `yahtzee/play.py`.

### What Stays Out of Config

- `cheat` and `cheatpercent` remain columns on `__table`. They're
  well-understood, used by existing services, and moving them is a separate
  refactor with unrelated risk. The new `config` column is additive, not a
  replacement.
- `reels` / `rows` in slots (see above).
- Yahtzee bonus rules (until the bonus exists in code).

### Files

**New:**
- `casino/src/casino/games/config.py` — `GameConfig` ABC, registry, `ConfigError`
- `casino/src/casino/games/configs/__init__.py` — built-in registrations
- `casino/src/casino/games/configs/blackjack.py`
- `casino/src/casino/games/configs/poker.py`
- `casino/src/casino/games/configs/slots.py`
- `casino/src/casino/games/configs/yahtzee.py`
- `casino/src/casino/sql/table_config_migration.sql` — additive column
- `casino/src/casino/tests/test_game_config.py`

**Edited:**
- `casino/src/casino/dal/table.py` — `create_table` accepts `config`;
  `get_table` / `list_tables` return it
- `casino/src/casino/services/table.py` — `TableService.create_table` and
  `update_table` accept `config`, validate via the registry
- `casino/src/casino/api/handler.py` — `_handle_create_table` and
  `_handle_update_table` pass `message["config"]` through
- `casino/src/casino/startup.py` — register the migration SQL

### Tests

`tests/test_game_config.py`:
- Round-trip: every `GameConfig` subclass serializes to dict and back
- Defaults: empty input → fully-populated default instance
- Validation: each field's bounds, types, and required-ness
- Registry: unknown game type → `ConfigError`; missing subclass → registry
  falls back to a `GenericConfig` no-op
- `update_table` with `config: {}` → column is reset to defaults
- Migration: existing tables without the column get backfilled to `'{}'`

### Implementation Order (delta on slots)

This work prepends to the slots implementation order:

1. `games/config.py` (ABC + registry)
2. `games/configs/{blackjack,poker,slots,yahtzee}.py`
3. `sql/table_config_migration.sql` + `startup.py` edit
4. `dal/table.py` edit (accept/return `config`)
5. `services/table.py` edit (validate via registry)
6. `api/handler.py` edit (pass `config` through)
7. `tests/test_game_config.py`
8. *Then* the original slots order (lib.py, dealer.py, …)
  - CLI: --autorestart/--no-autorestart, --restart-delay, --max-restarts
  - bed.json: bed.autorestart, bed.restart_delay, bed.max_restarts

---

## Slots v1.1: Single-Seater + Bed Integration Tests

Builds on the slots v1 commit (`e03e4b0`). Two changes:

### Single-Seater Enforcement

Slots v1 spec: a slots table has **at most one seated player**; spectators
may subscribe via `watch_table` but cannot take a second seat.
Multi-player (two players at the same slots table) is explicitly **v2**.

The existing `TableService.join_table` has no occupied-seat check and
blindly calls `add_player_to_table`, so the single-seater constraint is
enforced in the BED handler layer instead.

**Edit:** `casino/src/casino/api/handler.py` — `_handle_join_table`
- Fetch the table row before delegating to the service.
- If `table.type == "slots"`, count current seats via a direct
  `SELECT COUNT(*) FROM casino.__bank_table WHERE table_moniker = :m`.
- If count >= 1, return
  `{"type": "error", "code": "join_failed", "message": "Slots tables
  have a single seat; another player is already seated"}` *before*
  the service is called. The error code `join_failed` matches the
  existing convention for all join-failure cases.

`watch_table` is independent of seat occupancy — spectators can
subscribe to a slots table even when the seat is full.

### Bed Integration Test Suite

**Edit:** `casino/tests/test_slots_integration.py` — append a new class
`TestSlotBedIntegration(unittest.IsolatedAsyncioTestCase)` mirroring the
real-WebSocket pattern from `test_blackjack_flow.py`:
- Real `WebSocketServer` + `MessageRouter` boots.
- `WebSocketTestClient` is copied verbatim from
  `test_blackjack_flow.py` (~150 LOC).
- Test users: `jam-1` (player), `jam-2` (spectator), both with the
  standard `crypt('test', gen_salt('md5'))` password, 100000 credits,
  100000 bank balance.
- Skipped when `CASINO_TEST_DB` env var is unset.

**Coverage (20 test cases, every error path, both v1 seat scenarios):**

| # | Test |
|---|---|
| 1 | full spin flow: auth → create → join → spin → `slot_result` |
| 2 | `slot_paytable` returns the default paytable |
| 3 | `slot_history` returns spins in reverse-chronological order |
| 4 | spectator receives broadcast (alice plays, bob `watch_table`s, bob gets `slot_result` on the table channel) |
| 5 | player also receives own broadcast (direct reply + channel broadcast) |
| 6 | first `join_table` on a slots table succeeds |
| 7 | second `join_table` returns `error{code:"join_failed"}` |
| 8 | `watch_table` succeeds after the seat is full |
| 9 | `slot_spin` without auth → `not_authenticated` |
| 10 | `slot_spin` without `join_table` → `not_at_table` |
| 11 | bet below table minbet → `bet_below_min` |
| 12 | bet above table maxbet → `bet_above_max` |
| 13 | bet > bank balance → `insufficient_funds` |
| 14 | bet as a string → `invalid_bet` |
| 15 | `slot_spin` on a blackjack table → `wrong_game_type` |
| 16 | `slot_spin` on a missing table → `table_not_found` |
| 17 | stats: 5 spins → `slots.spins=5`, `slots.wins` consistent, `slots.net = sum(payout)-sum(bet)`, `slots.biggest_win = max(payout)` |
| 18 | `casino.__slot_spin` row count matches spin count |
| 19 | bank balance reconciles over 10 spins |
| 20 | re-auth after disconnect allows a fresh spin |

### Door-Mode Status

Door mode (currently `slots/play.py` + `slots/game.py`) is **retained**
in v1 as a thin TTY wrapper. BED (thin client) is the primary client;
the door mode remains available for direct terminal play. v2 may
deprecate the door mode in favor of a single BED-only flow.

### BED Wiring

No `bed/` code changes required. `MessageRouter.register_all` (which
the BED invokes at `bed/main.py:56` when given
`casino.api.handler.MessageRouter` as `--router`) already includes
`SlotServiceHandler` from the v1 commit. Slots registers automatically
the moment BED runs with casino's router.

### Files Touched

- `casino/src/casino/api/handler.py` — single-seater check in
  `_handle_join_table`
- `casino/src/casino/tests/test_slots_integration.py` — append
  `TestSlotBedIntegration` (20 cases + copied `WebSocketTestClient`)
- `casino/TODO.md` — this section

---

## Slots v1.2: theoretical_rtp Progress + Fast-Path

The original `Paytable.theoretical_rtp` was a full
``prod(strip_size)`` enumeration of every possible spin outcome.
At the v1 default reel sizes (33 × 32 × 32 × 32 × 32 = 34.6M
outcomes) this took minutes with **no output**, so users had no
feedback that the call was alive.

Two changes:

### 1. Per-Paytable-Key Fast-Path

`theoretical_rtp` now enumerates only the first ``k`` reels over
the *distinct symbol set* of each paytable key, weighted by
per-reel symbol occurrence counts in the strip. The remaining
``num_reels - k`` reels can be anything, so the count for that
entry is multiplied by ``prod(strip_size for strip in reels[k:])``.
This is **exact** (same answer as the brute force) but orders of
magnitude cheaper — sub-millisecond at default reel sizes, vs.
minutes for the brute force.

### 2. Progress Bar via `bbsengine6.io.screen.updateprogress`

`theoretical_rtp` accepts two new keyword-only arguments:

- `progress_every: int = 0` — default `0` preserves the silent
  behavior for existing callers and tests. When `> 0`, the function
  calls `bbsengine6.io.screen.updateprogress(done, total)` every N
  outcomes processed.
- `progress_total: int | None = None` — defaults to the total number
  of outcomes (`prod(strip_sizes)`). Callers can override.

The screen import is **lazy** (`from bbsengine6.io import screen`)
and any screen import failure or call failure is silently swallowed
so the RTP result is always returned. This means the function is
safe to call from contexts where `screen.init()` has not been run
(tests, library use, etc.).

### CLI Surface

`casino/slots/__main__.py` adds an `--rtp-progress N` flag that
plumbs `progress_every=N` to `theoretical_rtp` in both the smoke
mode and the demo mode. With `screen.init()` active, the user sees
the same `Progress [NN%]: [#####...]` bottom bar used by the rest
of the BBS engine.

### Test Coverage

Three new tests in `test_slots_unit.py::TestRTP`:

- `test_theoretical_rtp_with_progress_callback` — patches
  `bbsengine6.io.screen.updateprogress`, calls with
  `progress_every=1`, asserts the callback was called and that
  the returned RTP matches the no-progress result exactly.
- `test_theoretical_rtp_silent_when_progress_zero` — default
  `progress_every=0` must not touch the screen module (regression
  guard for the no-progress path).
- `test_theoretical_rtp_screen_import_failure_is_safe` — even with
  `progress_every > 0`, a missing or broken `screen` module is
  non-fatal.

The two pre-existing `TestRTP` tests (empirical and theoretical
band) are unchanged and continue to pass.

### Performance

| variant | reel size | runtime (no progress) |
|---|---|---|
| brute force (v1.0/v1.1) | 33 × 32⁴ = 34.6M | minutes |
| per-key fast-path (v1.2) | 33 × 32⁴ = 34.6M | ~0.1 ms |

Test suite runtime dropped from ~56 s to ~0.5 s.

### Files Touched

- `casino/src/casino/slots/lib.py` — `theoretical_rtp` rewritten
  with the fast-path and progress kwargs
- `casino/src/casino/slots/__main__.py` — `--rtp-progress N` flag
- `casino/src/casino/tests/test_slots_unit.py` — three new
  `TestRTP` cases
- `casino/TODO.md` — this section

---

## Yahtzee v1: BED-only, single-player, hybrid protocol

Adds yahtzee to the casino as a BED-only game. Replaces the legacy
door-mode stub at `casino/src/casino/yahtzee/` with a service-based
implementation behind a new `YahtzeeServiceHandler` registered in
`MessageRouter.register_all`.

### Bank model

Mirrors blackjack's BED flow:

- Player money: `engine.__member.credits`. Debit on bet, credit on
  payout, via `dal_bet.place_bet` / `dal_bet.settle_bet`. One
  `__betlog` row per session (single bet at start of session,
  settled round-by-round).
- Table treasury: `bank.__account` keyed on `table_moniker`, via
  `__bank_table` mapping. Auto-created by
  `services.table.TableService.create_table` (no yahtzee-specific
  bank code).
- One `__log` row per turn for audit (`message='yahtzee_turn'`,
  `attrs={"turn": n, "category": ..., "score": v, "net": v,
  "rake": 0}`).
- `__table` row stays `status='open'` across sessions; reused by
  `quick_play` on the next session.
- One `__game` row per session; closed at end of 13th round.
  `__table` is **not** closed.
- `RAKE_PERCENT = 0` in v1; rake math is implemented in
  `lib.net_payout` but short-circuited to return `score` unchanged.
  Re-enable when adding multiplayer in v2.

### BED message protocol (hybrid)

Server owns randomness; client owns choices. New message types
added to `api/messages.py:MessageType`:

- `yahtzee_quick_play` (C→S) — lazily creates/reuses a hidden
  yahtzee table owned by the player, opens a `__game` row, places
  the session bet (table's `minimumbet`), returns initial
  `yahtzee_state`.
- `yahtzee_roll` (C→S) — server rolls the 5 dice, decrements
  `rolls_left` from 2 to 1.
- `yahtzee_reroll` (C→S) `{locks: [int, ...]}` — sets held dice
  per the lock indices, rolls unlocked dice, decrements
  `rolls_left`.
- `yahtzee_score` (C→S) `{category: str}` — computes
  `value = lib.score(dice, category)`, credits the player via
  `dal_bet.settle_bet`, writes the per-turn `__log` row, advances
  the round, resets `rolls_left = 2`.
- `yahtzee_state` (S→C) — broadcast to the
  `casino:table:{moniker}` channel after every successful state
  change. Payload: `table_moniker, round, dice[5], locked[5],
  rolls_left, scorecard{13}, running_total, last_score, is_over`.
- `yahtzee_result` (S→C) — sent once at the end of the 13th
  round. Payload: `table_moniker, final_scorecard, upper_total,
  lower_total, grand_total, rake_total, new_balance`.

Server-side rules (enforced in `YahtzeeService`):

- `yahtzee_roll` allowed only at start of a round
  (`rolls_left == 2`).
- `yahtzee_reroll` allowed when `rolls_left > 0`.
- `yahtzee_score` allowed any time the round is active. Validates
  category is one of the 13 and is currently `None` in the
  scorecard. Player may score early (before exhausting rolls).
- Each successful state change publishes `yahtzee_state` to
  `casino:table:{table_moniker}` so spectators see the dice.
- On `yahtzee_score` that completes the game, sets
  `__game.status = 'closed'`, sends `yahtzee_result` to the
  player, removes the game from `_games`. `__table` stays open.
- Disconnect mid-game: `finalize_on_disconnect` settles the open
  bet as a loss, sets `__game.status = 'cancelled'`. Hooked into
  `MessageRouter.unregister_session`.

### File layout

```
src/casino/yahtzee/
├── __init__.py            # REWRITE: BBS module shims only
├── lib.py                 # NEW:    constants, scoring, rake (0), net_payout
├── dealer.py              # NEW:    YahtzeeDealer — 5 dice, locked set
├── service.py             # NEW:    YahtzeeGame + YahtzeeService (in-memory registry)
├── api_handler.py         # NEW:    YahtzeeServiceHandler — BED dispatch
├── README.md              # REWRITE: v1 BED protocol docs
├── Makefile               # KEEP
├── yahtzee1.png           # KEEP (unused asset)
├── play.py                # DELETE (legacy 74-line stub)
├── __main__.py            # DELETE
└── testshowdice.py        # DELETE (legacy ttyio5 script)

src/casino/api/handler.py  # EDIT: register YahtzeeServiceHandler in register_all
src/casino/api/messages.py # EDIT: add 6 entries to MessageType enum
src/casino/main.py         # EDIT: drop the "Y" Yahtzee menu entry
src/casino/tests/
├── test_yahtzee_lib.py    # NEW (commit 1)
├── test_yahtzee_dealer.py # NEW (commit 1)
├── test_yahtzee_service.py # NEW (commit 2)
└── test_yahtzee_handler.py # NEW (commit 3)
```

### Commits (3)

1. **Pure engine** — `yahtzee/lib.py`, `yahtzee/dealer.py`,
   `tests/test_yahtzee_lib.py`, `tests/test_yahtzee_dealer.py`.
   No DB, no I/O, no BED. ~400 lines, 2 test files.
2. **Service + bank integration** — `yahtzee/service.py`,
   `tests/test_yahtzee_service.py`. `YahtzeeGame` (per-table
   state) + `YahtzeeService` (in-memory `_games` registry, mirrors
   `PokerService._tables`). Calls `dal_bet.place_bet` /
   `settle_bet`, `services.table.TableService.create_table`,
   `database.connect` for log rows. ~350 lines, 1 test file.
3. **BED handler + integration** — `yahtzee/api_handler.py`,
   `tests/test_yahtzee_handler.py`. Edits `api/handler.py`
   (register handler, hook disconnect cleanup), `api/messages.py`
   (6 enum entries), `main.py` (drop "Y" entry). Deletes
   `yahtzee/play.py`, `yahtzee/__main__.py`,
   `yahtzee/testshowdice.py`. Rewrites `yahtzee/__init__.py` (BBS
   shims only) and `yahtzee/README.md` (v1 protocol docs). ~200
   lines + edits + deletes, 1 test file.

### Out of scope (v1)

- `games/config.py` registry + `YahtzeeConfig`. Hardcoded
  `RAKE_PERCENT=0`, `MIN_BET=10`, `MAX_BET=1000` in
  `yahtzee/lib.py`.
- Scorecard persistence (in-memory only; final scorecard in
  `__log.attrs` of the closing log row + the `yahtzee_result`
  payload).
- Player stats (no `casino.__player.stats` keys added).
- Upper-section bonus, yahtzee bonus, joker rule.
- Multiplayer (`YahtzeeService._games` is keyed on
  `table_moniker`; v1 assumes one player per session because the
  bank/scoring logic assumes the player is the table owner).
- Door-mode `play.py` (deleted).
- Top-level `Y` menu shortcut in `main.py` (removed; players
  reach yahtzee via the existing `Create` + `Join` flow).
- `cmd_yahtzee_quick_play()` helper in `client/casino_client.py` for the
  BBS-side client (a future commit can wrap the BED messages for
  door-mode use).

### Verification per commit

- `pytest src/casino/tests/` green, `ruff` clean on all new files.
- Commits 1 and 2 are fully mocked (no live DB).
- Commit 3 is fully mocked for the handler tests. Manual smoke
  (if a live BED is available, not mandated): start `casino.bed`,
  connect via `client/casino_client.py`, `Create` a yahtzee table, `Join`,
  exercise `yahtzee_roll` / `yahtzee_reroll` / `yahtzee_score`
  via a debug BED message sender (out of scope to add).

---

## Seats per Table — Blackjack & Poker Capacity Model

**Status:** Planned

A unified capacity model for how many players a casino table can hold,
parameterized by game type, surfaced consistently through the
`create_table` / `update_table` / `join_table` / `list_tables` /
`get_table_state` API.

> **Related**: see "AI bot players" (item 14) in "Blackjack Missing
> Features" — that feature depends on this capacity model landing
> first. The owner must be able to seat bots into the table up to
> `min_players` before the hand engine will start; the
> `services.table.can_start_hand` extension point defined here is
> the integration surface.

### Problem

The codebase currently has **three divergent seat counts** scattered
across modules, none of which are wired to the table row or the join
path:

- **Blackjack** — `blackjack/game.py:29-40` builds a single
  `BlackjackPlayer` and a single dealer, so a hand is hard-coded to
  **1 player vs. 1 dealer**. There is no concept of multi-player
  blackjack.
- **Poker** — `poker/variant/base.py:18-19` declares
  `min_players=2, max_players=10`; `poker/variant/texas_hold_em.py:8-9`
  and `omaha.py:8-9` repeat `max_players=10`; `seven_card_stud.py:8-9`
  uses `max_players=8`. These are class attributes on the variant, not
  columns on the table row.
- **Slots** — `api/handler.py:369-396` enforces a hard-coded
  "**single seat**" for `table.type == "slots"` (slots v1 invariant),
  counted via `SELECT COUNT(*) FROM casino.__bank_table WHERE
  table_moniker = :m`. (Wiring bug — see below.)
- **Poker in DAL** — `casino.dal.table.add_player_to_table`
  (`dal/table.py:232-244`) inserts into `casino.map_cardtable_player`
  with **no occupancy check** at all; only the BED handler's
  slots-specific check exists.

The `casino.__table` row has **no `min_players` / `max_players`
column**; per-table "how many can sit" lives in code, scattered by
game type, with no consistent read path for `get_table_state` or
`list_tables`.

### Goals

1. **One source of truth** for table capacity, keyed by `table.type`
   with per-table overrides.
2. **Pluggable per game type** so the same scheme covers blackjack,
   poker, slots, yahtzee, and future games.
3. **Validated at create / update time** (not at first join) so
   misconfiguration surfaces immediately.
4. **Enforced in `join_table`** before the player is added, with a
   clear `error` envelope back to the client.
5. **Surfaced in `list_tables` and `get_table_state`** so the lobby /
   TUI can show "3 / 7 seats taken".
6. **Spectator model stays separate** — spectators are unlimited and
   don't count against seat capacity (matches current slots v1
   behavior).
7. **Mid-hand joins rejected** across poker / blackjack / yahtzee —
   industry norm; late joiners wait for the next round.
8. **Poker variant floor respected** — the variant class attribute is
   the floor; `PokerConfig.max_players` can raise but never lower.
9. **Extension point for bot-fill** — `services.table.can_start_hand`
   exists and gates hand start on `min_players`, so the "AI bot
   players" feature (TODO item 14) can plug in without a refactor.

### Per-Game Defaults

| Game type   | Default `min_players` | Default `max_players` | Rationale |
|-------------|-----------------------|-----------------------|-----------|
| `blackjack` | 1                     | 7                     | Standard physical blackjack table seats 5–7 players; existing door-mode code is single-player, so 1 is the safe floor. Industry standard: 1-player minimum is acceptable (one human vs. house dealer). |
| `poker`     | 2                     | 10                    | Matches `poker/variant/base.py` defaults. Seven-Card Stud overrides variant max to 8 (`seven_card_stud.py:9`). Effective max per table = `max(variant.max_players, config.max_players or variant.max_players)`. |
| `slots`     | 0                     | 1                     | Slots v1 invariant from `api/handler.py:369-396` — single seat, spectators unlimited. `min_players=0` lets a table sit empty between sessions. |
| `yahtzee`   | 1                     | 6                     | Roll-and-pass supports up to 6; standard Yahtzee cap. |

Defaults are encoded in a new `GameCapacityRegistry` (mirroring the
`GameTypeConfigRegistry` and `VariantRegistry` patterns in
`casino/games/config.py` and `casino/poker/variant/__init__.py`).

### Wire Shape

`create_table` (additive, optional):

```json
{ "type": "create_table",
  "game_type": "poker",
  "min_bet": 1, "max_bet": 1000,
  "config": { "min_players": 2, "max_players": 9, "variant": "texas_hold_em" } }
```

`update_table` semantics match the "Generic Per-Game Config" section:
`config: {}` resets to defaults; partial overrides are replaced
wholesale in v1.

`list_tables` and `get_table_state` return:

```json
{ "moniker": "NorthAlpha", "game_type": "poker",
  "min_players": 2, "max_players": 10,
  "seats_taken": 4, "seats_available": 6,
  "players": ["alice","bob","carol","dave"],
  "spectators": [...] }
```

`join_table` error envelopes:

```json
{ "type": "error", "code": "join_failed",
  "message": "Table is full (4/4 seats taken)" }
```

```json
{ "type": "error", "code": "join_failed",
  "message": "Hand in progress; try again at next shuffle" }
```

(Reuses the existing `join_failed` error code from
`api/handler.py:391`.)

### Storage

Add **two columns** to `casino.__table` via an additive migration,
mirroring the pattern from `sql/hidden_table_migration.sql` and the
planned `sql/table_config_migration.sql`:

```sql
-- sql/table_capacity_migration.sql
alter table casino.__table
    add column if not exists "min_players" integer;
alter table casino.__table
    add column if not exists "max_players" integer;
```

Both columns nullable. On read, `dal/table.get_table` and `list_tables`
resolve `None` → `GameCapacityRegistry.get(table.type).defaults`
(single source of truth, not stored in DB). This avoids backfilling
every existing row and keeps the registry as the canonical default.

`PokerConfig` (from the "Generic Per-Game Config" section above)
already declares `min_players` and `max_players`; the `__table`
columns and the config schema stay in sync: write goes through
`config`, read back-fills from the registry if the columns are `NULL`.

### Capacity Resolution Rules

**Generic (blackjack / slots / yahtzee):**

- `effective_min = config.min_players or registry.defaults.min_players`
- `effective_max = config.max_players or registry.defaults.max_players`
- Validation at `create_table` / `update_table`:
  - `0 <= min_players <= max_players <= sanity_cap`
  - sanity caps: blackjack=7, slots=1, yahtzee=6

**Poker (variant floor, config raises only):**

- `variant_min = 2`, `variant_max = variant.max_players` (e.g., 8 for
  Stud, 10 for Hold'em/Omaha)
- `effective_min = config.min_players or 2`, bounded `[2, effective_max]`
- `effective_max = config.max_players or variant_max`, validated
  `>= variant_max` (config can raise, never lower)
- Upper sanity cap: `23` (physical table limit; matches the 26-letter
  phonetic alphabet range used in `dal/table.py:11-17` minus a few)

The `GameCapacityRegistry.get(game_type, config=None) -> GameCapacity`
helper centralizes this logic and is the single entry point for both
write-time validation and read-time resolution.

### Join-Time Enforcement

`join_table` checks (in order):

1. **Generic capacity**: `seats_taken >= effective_max` → `join_failed`
   "Table is full (N/M seats taken)".
2. **Mid-hand rejection (poker / blackjack / yahtzee)**:
   - Fetch the active game for the table: `casino.__game` row where
     `tablemoniker = :m` and
     `status NOT IN ('settled', 'cancelled')`.
   - If a row exists (hand in progress), reject with `join_failed`
     "Hand in progress; try again at next shuffle".
   - Slots has no multi-step "hand" — one spin is one event — so
     step 2 does not apply. Capacity alone is the gate.
3. **Spectator immunity**: `watch_table` is independent of seat
   occupancy (matches `api/handler.py:393-396`).

### Wiring Bug to Fix

The current slots check in `api/handler.py:391` counts
`casino.__bank_table` rows. The DAL already has
`dal/table.get_table_players(args, moniker)` (`dal/table.py:206-216`)
which queries `casino.map_game_player` joined to `casino.__game`. The
join-table check should use that helper, not a raw `COUNT(*)` on
`__bank_table` (which is a 1:1 bank-account table, not a seat map).
The new capacity work consolidates on `get_table_players` + a
`min_players/max_players` check in the DAL/service layer, and the
slots branch in `api/handler.py:369-396` is removed in favor of the
unified path.

### Hand-Start Extension Point

A new `services/table.can_start_hand(args, table, players) ->
tuple[bool, str]` helper gates hand start:

- Returns `(True, "ok")` when `len(players) >= effective_min`.
- Returns `(False, f"Need at least {effective_min} players; have
  {len(players)}")` otherwise.

This is **purely an extension point** in v1. The bot-fill feature
(TODO item 14) plugs in by:

1. Calling `can_start_hand` before dealing.
2. If `False`, the owner (or a sysop) may invoke a new
   `fill_with_bots` action; if `table.attrs["auto_fill_bots"] = true`,
   the service auto-fills.
3. The bot-fill *implementation* (which bot, what strategy, what
   stats) is out of scope for the capacity work — it lands with item
   14.

The hand engines call `can_start_hand` from:

- `services/game.py` (blackjack round start)
- `services/poker.py` (poker hand start; replaces the inline
  `if len(table.players) < table.min_players` check at
  `services/poker.py:229-230`)

This makes item 14 a clean follow-up: add `fill_with_bots`, call it
before the `can_start_hand` check, no other refactor required.

### Files

**New:**

- `casino/src/casino/games/capacity.py` — `GameCapacity` dataclass,
  `GameCapacityRegistry`, per-game-type defaults,
  `get_capacity(game_type, config=None) -> GameCapacity`
- `casino/src/casino/sql/table_capacity_migration.sql` — additive
  columns

**Edited:**

- `casino/src/casino/dal/table.py` — `get_table` and `list_tables`
  populate `min_players`, `max_players`, `seats_taken`,
  `seats_available`; `add_player_to_table` no longer capacity-checks
  (moved to service); raw `__bank_table` count removed
- `casino/src/casino/services/table.py` — `join_table` does the
  unified capacity + mid-hand check; `create_table` / `update_table`
  validate the config via the registry; new `can_start_hand` helper
- `casino/src/casino/api/handler.py` — `_handle_join_table` routes all
  game types through the unified capacity check; the slots-only
  branch at `api/handler.py:369-396` is removed
- `casino/src/casino/services/poker.py` — replace the inline
  `if len(table.players) < table.min_players` check at
  `services/poker.py:229-230` with a call to `can_start_hand`
- `casino/src/casino/services/game.py` — blackjack round start calls
  `can_start_hand`
- `casino/src/casino/startup.py` — register the migration SQL
- `casino/src/casino/games/config.py` — `PokerConfig` validation:
  `config.max_players >= variant.max_players`;
  `config.max_players <= 23`

**Cross-reference edits:**

- TODO line 238 (item 14, "AI bot players"): add a one-line
  prerequisite note at the top: `> Prerequisite: "Seats per Table"
  capacity model must land first. The owner must be able to seat bots
  up to min_players before the hand engine starts; the
  services.table.can_start_hand extension point is the integration
  surface.`

### Test Coverage

`tests/test_table_capacity.py`:

- **Defaults**:
  - `test_blackjack_default_capacity` — no config; `min_players=1,
    max_players=7`
  - `test_poker_default_capacity` — no config; `min_players=2,
    max_players=10`
  - `test_poker_seven_card_stud_default_capacity` — `max_players=8`
    (variant-specific floor)
  - `test_poker_seven_card_stud_config_raises_max` —
    `config: {max_players: 10}`; effective max 10
  - `test_slots_single_seat_default_capacity` — `max_players=1`;
    second `join_table` → `join_failed`
  - `test_yahtzee_default_capacity` — `min_players=1, max_players=6`
- **Custom config**:
  - `test_custom_capacity_in_config` — poker `config: {max_players:
    4}`; fifth `join_table` rejected
  - `test_invalid_capacity_min_greater_than_max` —
    `config: {min_players: 5, max_players: 3}` → `invalid_config`
  - `test_poker_config_max_below_variant_max_rejected` — Stud with
    `config: {max_players: 6}` → `invalid_config`
  - `test_poker_config_max_above_variant_max_accepted` — Stud with
    `config: {max_players: 10}` → accepted, effective max is 10
  - `test_poker_max_above_sanity_cap_rejected` —
    `config: {max_players: 24}` → `invalid_config`
- **Spectator model**:
  - `test_capacity_unrelated_to_spectators` — fill all seats; 10
    spectators `watch_table`; all allowed
- **List / state surface**:
  - `test_list_tables_shows_seats_taken_and_available` — fill 3 of 5;
    row has `seats_taken=3, seats_available=2`
- **Update flow**:
  - `test_update_table_can_raise_capacity` — owner
    `config: {max_players: 6}`; existing 4 seated unaffected
  - `test_shrinking_capacity_below_current_occupancy_rejected` — 4
    seated, `config: {max_players: 2}` → `invalid_config` (cannot
    leave players stranded over the cap)
- **Leave / free seat**:
  - `test_leave_table_frees_seat` — player leaves; `seats_taken`
    decrements
- **Capacity-zero (slots)**:
  - `test_capacity_zero_min_players_allows_empty_table` — slots table
    with no seated players; spin still permitted
- **Mid-hand rejection**:
  - `test_poker_join_rejected_mid_hand` — start a hand with 3/10
    seated; 4th `join_table` → `join_failed` "Hand in progress";
    after hand settles, the same `join_table` succeeds
  - `test_blackjack_join_rejected_mid_hand` — same shape for
    blackjack
  - `test_yahtzee_join_rejected_mid_hand` — same shape for yahtzee
  - `test_slots_allows_join_anytime` — slots has no multi-step hand;
    `join_table` between spins is allowed (and a 2nd joiner is
    rejected only on capacity, not "mid-spin")
- **Blackjack floor**:
  - `test_blackjack_single_player_hand_starts` — owner alone,
    `min_players=1`, hand starts (regression guard for the floor at 1)
- **Hand-start extension point**:
  - `test_can_start_hand_true_when_at_min` — 2/2 poker; returns
    `(True, "ok")`
  - `test_can_start_hand_false_when_below_min` — 1/2 poker; returns
    `(False, "Need at least 2 players; have 1")`
  - `test_poker_hand_start_uses_can_start_hand` — replace the inline
    check at `services/poker.py:229-230`; verify the call site
    delegates
- **Door-mode compat**:
  - `test_door_mode_compat` — door-mode blackjack with the new column
    still works (regression guard for the migration)

### Out of Scope (v1)

- **Multi-player blackjack** (a single hand shared by N players vs.
  one dealer). The capacity model permits 1–7 players at a blackjack
  table, but the **hand engine** in `blackjack/hand.py` and
  `blackjack/phase.py` is still single-player in v1. The capacity
  column is forward-compatible: it permits the seat count without yet
  wiring the dealer to deal N hands per round. Multi-player blackjack
  is its own workstream that consumes this capacity model when it
  lands.
- **AI bot players filling empty seats** (TODO line 238, item 14). The
  capacity check is independent of *who* fills the seat. The
  extension point (`can_start_hand`) is in place; the bot-fill
  implementation lands with item 14.
- **Per-variant poker override UI** — the API accepts the override;
  the lobby/TUI rendering of "Stud: 2–8" or "Stud: 2–10
  (operator-raised)" is a follow-up.
- **Spectator caps** — explicitly unlimited by design; matches
  `api/handler.py:393-396` ("Spectators can watch via `watch_table`
  but cannot take a second seat").
- **Auto-fill-bots policy details** — `attrs["auto_fill_bots"]` is
  read by the extension point; the policy (which bot, what difficulty,
  what stats) is item 14's concern.

### Resolved Decisions

1. **Mid-hand poker join**: REJECTED. Industry norm.
2. **Variant floor / config raises only**: Variant class attribute is
   the floor; `PokerConfig.max_players` can raise but not lower.
3. **Bot fill at hand start**: `services/table.can_start_hand` gates
   hand start on `min_players`; the owner (or a sysop) may invoke a
   new `fill_with_bots` action; `attrs["auto_fill_bots"]=true` enables
   auto-fill. Bot-fill *implementation* lands with TODO item 14.
4. **Blackjack `min_players=1` floor**: Confirmed. Single-player
   blackjack is valid in BED mode, matching door mode.
5. **Yahtzee mid-hand join**: same `Hand in progress` rejection as
   poker/blackjack (consistency).
6. **Cross-reference to item 14**: two-way pointer; item 14 gains a
   prerequisite note, and this section points back.

### Implementation Order

1. `games/capacity.py` (registry + dataclass + defaults +
   variant-aware poker resolution)
2. `sql/table_capacity_migration.sql` + `startup.py` edit
3. `dal/table.py` edit (return `min_players`, `max_players`,
   `seats_taken`, `seats_available`; remove the `__bank_table` count)
4. `services/table.py` edit (`join_table` unified capacity + mid-hand
   check; `create_table` / `update_table` validation; new
   `can_start_hand` helper)
5. `api/handler.py` edit (remove slots-only branch; route all game
   types through the unified path)
6. `services/poker.py` edit (replace inline `min_players` check at
   line 229-230 with `can_start_hand`)
7. `services/game.py` edit (blackjack round start calls
   `can_start_hand`)
8. `games/config.py` edit (`PokerConfig.max_players >=
   variant.max_players` and `<= 23` validation)
9. Cross-reference: TODO line 238 (item 14) gains a one-line
   prerequisite note
10. `tests/test_table_capacity.py`
11. Lint, typecheck, full pytest suite

---

## Compliance, AML, Responsible Gambling & Data Protection (Reference)

Reference material covering casino regulatory topics (KYC/AML, responsible
gambling, data protection). Items added here are research / awareness
inputs, not implementation tasks — pull items into the implementation
sections above (or new sections) when a concrete feature is scoped.

- [ ] Sum&Substance — "A complete guide to casino compliance: AML, responsible gambling, and data protection"
  https://sumsub.com/blog/a-complete-guide-to-casino-compliance-aml-responsible-gambling-and-data-protection/

### Jurisdiction: operator location vs. server location (US)

When the operator is in one US state and the servers are in another, both
jurisdictions apply, and several federal statutes sit on top:

1. **Operator's home state** — the state where the business is conducted.
   Most state gambling statutes (e.g., SC Code §16-19-40 "Unlawful games and
   betting" and §16-19-130 "Betting, pool selling, bookmaking and the like
   prohibited") make it a crime to *operate* a gambling business from
   within the state regardless of where the servers sit. So if the operator
   is in a state that prohibits casino-style gambling, the operator is
   liable there even if servers are elsewhere.
2. **Server's state** — the state where the hardware physically resides.
   That state may license, regulate, or prohibit the activity. Hosting
   unlicensed gambling software can be a separate violation of the
   server's state law.
3. **Customer's state** — the state where the bettor is located when the
   bet is initiated. UIGEA (31 USC §5362) and the Wire Act (18 USC §1084)
   key off "the place where the bet is made or received" — not the
   server. So the customer's state is also a controlling jurisdiction.
4. **Federal overlay** — the Wire Act (interstate transmission of
   sports-bets), UIGEA (payment processing for unlawful internet
   gambling), and the Bank Secrecy Act (FinCEN CTRs / SARs from
   "gambling businesses") all apply on top of state law.

Practical guidance:

- **Pick the most-restrictive state among {operator, server, customer}**
  and design for that. Don't assume server location alone answers the
  question.
- **South Carolina is one of the strictest**: no commercial casinos, no
  racetrack betting, no online gambling, no sports betting. The only
  legal gambling in SC is the SC Education Lottery (SC Code §16-19-40
  et seq.; video poker banned 2000-07-01; see also "Gambling in the
  United States" state-by-state table). Operating a casino from SC, or
  serving SC customers from anywhere, is a §16-19-40 / §16-19-130
  violation.
- **Never accept a SC resident as a customer** without confirming the
  activity is lawful in SC at the time of the bet. Server location is
  irrelevant to that analysis.

References (US):

- [ ] 31 USC §§ 5361–5367 — Unlawful Internet Gambling Enforcement Act (UIGEA) of 2006
  https://www.law.cornell.edu/uscode/text/31/5361
- [ ] 18 USC § 1084 — Federal Wire Act (Transmission of wagering information)
  https://en.wikipedia.org/wiki/Federal_Wire_Act
- [ ] DOJ Office of Legal Counsel, 2011 opinion (Wire Act applies only to sports betting)
  cited via Wikipedia: https://en.wikipedia.org/wiki/Federal_Wire_Act
- [ ] DOJ OLC, 2018 opinion reversing 2011 (Wire Act covers all gambling)
  cited via Wikipedia: https://en.wikipedia.org/wiki/Federal_Wire_Act
- [ ] Bank Secrecy Act (BSA) of 1970 — anti-money-laundering / CTR / SAR
  https://en.wikipedia.org/wiki/Bank_Secrecy_Act
- [ ] FinCEN — "Casino regulations under the Bank Secrecy Act" (BSA applies to gambling businesses)
  referenced via Wikipedia: https://en.wikipedia.org/wiki/Bank_Secrecy_Act
- [ ] South Carolina Code of Laws, Title 16, Chapter 19 — Gambling and Lotteries
  https://www.scstatehouse.gov/code/t16c019.php
  (in particular §16-19-40 "Unlawful games and betting" and §16-19-130
  "Betting, pool selling, bookmaking and the like prohibited")
- [ ] SC Code §16-19-40 — Unlawful games and betting (misdemeanor, fine up to $100, jail up to 30 days for player; up to $2,000 fine, 12 months for operator)
  https://www.scstatehouse.gov/code/t16c019.php
- [ ] SC Code §16-19-130 — Pool selling / bookmaking prohibited (misdemeanor, fine up to $1,000, jail up to 6 months)
  https://www.scstatehouse.gov/code/t16c019.php
- [ ] "Gambling in the United States" — Wikipedia (state-by-state table; SC: No/No/No for charitable, pari-mutuel, lottery, video lottery, commercial, racetrack, online, sports betting)
  https://en.wikipedia.org/wiki/Gambling_in_the_United_States
- [ ] "Unlawful Internet Gambling Enforcement Act of 2006" — Wikipedia
  https://en.wikipedia.org/wiki/Unlawful_Internet_Gambling_Enforcement_Act_of_2006
- [ ] "Online gambling" — Wikipedia (US section; UIGEA, Wire Act, and US online-gambling overview)
  https://en.wikipedia.org/wiki/Online_gambling

---

## `casino/dal/player.py:92` crashes on `NULL` credits

### Problem

`casino/src/casino/dal/player.py:92` reads a member's balance as:

```python
return int(row["credits"]) if row else 0
```

`row["credits"]` is `None` whenever `engine.__member.credits`
is `NULL` (the default for any new member row), which makes
the `int(None)` call raise:

```
TypeError: int() argument must be a string, a bytes-like object or
a real number, not 'NoneType'
```

The exception propagates out of `PlayerService.authenticate`
(`casino/src/casino/services/player.py:51`) and surfaces to
the BED client as:

```json
{"type": "error", "code": "service_error",
 "message": "int() argument must be a string, a bytes-like object
              or a real number, not 'NoneType'"}
```

**Net effect:** every member in the database who has never
had a credit transaction crashes on `auth`. That includes
every freshly-created test user — `alice`, `bob`, `jam`,
`socrates_test_user`, `vulcan_test_user`,
`teos_integration_test_user`, etc. in the `zoid6test`
database. A working casino bring-up therefore requires a
one-time `UPDATE engine.__member SET credits = 1000 WHERE
credits IS NULL` (or equivalent) before any client can log
in. The smoke test on 2026-06-28 hit this; the workaround
is documented in the chat history.

The bug surfaced during the bed+casino bring-up against
`zoid6test`. The `engine.__member.credits` column is
`numeric(10,0)`, nullable, no default. The DAL assumes
non-NULL.

### Why this matters

- **Production breakage.** Any new member who hasn't
  received a credit transaction yet will fail `auth` with
  a `service_error`. The user sees a Python traceback
  message, not a friendly "balance unavailable" — this
  leaks internal implementation details to clients.
- **Test setup fragility.** The smoke test
  (`/tmp/bed-logs/smoke.py`) and any future integration
  test against a fresh database has to remember to seed
  `credits`. The fix is one line of SQL or one line of
  Python; whichever lands, the workaround should not
  exist in user-facing docs.
- **The pattern is repeated.** Other DAL reads in casino
  (e.g. `casino/src/casino/dal/table.py`, `dal/bank.py`)
  may have the same `int(row["x"])` shape. None of those
  are reported broken today, but the audit below is worth
  doing once.

### Fix options

#### Option A — Python-side null-safe coercion (one-line)

Change
`casino/src/casino/dal/player.py:92` from

```python
return int(row["credits"]) if row else 0
```

to

```python
return int(row["credits"]) if row and row["credits"] is not None else 0
```

(or `int(row["credits"] or 0)`, which is shorter and
equivalent for `numeric` columns that round-trip as
`Decimal` or `int` — `None` and `0` are the only falsy
values).

- **Pros:** Tiny diff. No schema change. Stays close to the
  existing logic. Existing callers see `0` for a new
  member, which is the safe default.
- **Cons:** Pushes the null-handling into every DAL call
  site individually. Future column reads could reintroduce
  the same bug.

#### Option B — SQL-side `COALESCE` (one-line at the SELECT)

Change the SELECT in
`casino/src/casino/dal/player.py:80-90` from
`SELECT credits FROM engine.__member WHERE moniker = %s`
to
`SELECT COALESCE(credits, 0) AS credits FROM engine.__member WHERE moniker = %s`. The Python side becomes
`return int(row["credits"]) if row else 0` again, and
`None` is never seen by the application.

- **Pros:** Same diff size as A. The fix lives at the
  data-shape boundary, which is the right layer. Other
  DAL readers can adopt the same `COALESCE(..., 0)` pattern
  for their `numeric` columns.
- **Cons:** A future `credits` column that legitimately
  could be NULL (e.g. "balance not yet computed") would
  silently become `0`. For `numeric(10,0)` balance columns
  this is fine; for nullable "amount" or "rate" columns
  the pattern is wrong.

#### Option C — schema-side `NOT NULL DEFAULT 0` migration

Add a migration that runs
`ALTER TABLE engine.__member ALTER COLUMN credits SET DEFAULT 0, ALTER COLUMN credits SET NOT NULL`
and backfill existing rows. The DAL code stays as-is.

- **Pros:** Fixes the bug at the data layer; no
  application-side null handling needed. Future inserts
  without an explicit `credits` value get `0`.
- **Cons:** Cross-schema migration; affects every consumer
  of `engine.__member.credits` (bbsengine6 bank service,
  zoid6, empyre, murdermotel, mistermcfeely, casino).
  Not all of those want `NOT NULL` — empyre's player
  `coins` is nullable on purpose (player can have 0 coins
  is the default, but the schema was written before the
  convention was standardized). The risk of cascading
  breakage is non-trivial.

### Recommendation: A + C, phased

Phased approach: ship A in the casino repo this week (no
coordination, fixes the immediate crash), land C in a
follow-up bbsengine6-flavored PR (permanent fix at the
schema layer). A and C are complementary, not alternatives.

**Phase 1 — casino-only, ships now (Option A):**

Read-site null check at `casino/src/casino/dal/player.py:92`.
Smallest possible diff; no SQL change; no schema migration;
no cross-repo coordination. The fix is local to the
function that crashes; the underlying nullable column
stays nullable, so this is a bandage.

The schema for `engine.__member.credits` is `numeric(10,0)`
nullable with no default — a NULL row remains NULL after the
read. Phase 1 fixes the crash, not the data shape.

**Phase 2 — bbsengine6 follow-up (Option C):**

Schema migration to `NOT NULL DEFAULT 0` on
`engine.__member.credits`, with a backfill of existing NULL
rows. Once C lands and is deployed, the Option-A read-site
check in `get_player_balance` becomes dead code and can be
reverted. This is the permanent fix; see "Phase 2 — schema
migration" below for the detailed plan.

**Why not Option B (SQL `COALESCE`) alone:** Option B's
`COALESCE(..., 0)` pattern is the right convention for
nullable balance reads, and `bbsengine6.bank.account` does
use it. But applying B to `get_player_balance` would leave
the underlying column nullable, and other consumers of
`engine.__member.credits` (zoid6, empyre, murdermotel,
mistermcfeely) would still see NULL. Option A is the same
one-line diff and keeps the fix in the function that
crashes; once C lands, both A's defensive check and B's
COALESCE become unnecessary.

### Tasks

- [X] **Apply Option A to `casino/src/casino/dal/player.py:81-94`**.
  Read-site check: `if row and row["credits"] is not None:
  return int(row["credits"]); return 0`. SQL unchanged.
- [X] **Audit other `int(row["…"])` call sites in casino**:
  - `grep -rn "int(row\[" casino/src/casino/dal/`
  - See "Audit results" below for the per-site decisions.
- [X] **Remove the workaround** from the bring-up notes:
  the `UPDATE engine.__member SET credits = 1000 WHERE credits IS NULL`
  step documented in the 2026-06-28 chat history is no
  longer needed once the DAL is fixed. The smoke test
  comment block at `/tmp/bed-logs/smoke.py` has been
  updated to point at this fix.
- [X] **Add a regression test** in
  `casino/src/casino/tests/test_player_service.py` (new
  file): insert a member with `credits=NULL`, call
  `PlayerService.authenticate`, assert the call returns
  `balance=0` and does not raise. Also asserts the DAL
  read does not backfill NULL to 0 (Phase 1 is a read
  fix; the column stays nullable until C).
- [X] **Update the smoke test** at `/tmp/bed-logs/smoke.py`
  comment block — drop the `psql -c "update engine.__member set credits=1000 where credits is null"`
  line; it's not needed anymore.

### Audit results

`grep -rn "int(row\[" casino/src/casino/dal/` returned 5
matches across 4 files. Decisions per site:

| File:Line | Column | Schema | Decision | Notes |
|---|---|---|---|---|
| `dal/player.py:93` | `engine.__member.credits` | `numeric(10,0)`, nullable, no default | A (read-site check) | **The original bug.** Fixed. |
| `dal/bet.py:45` | `engine.__member.credits` | same column as above | A (read-site check) | Same column, same bug class. Reading the column for a balance check before deducting. Fixed in the same pass. |
| `dal/slots.py:39` | `casino.__slot_spin.id` | `SERIAL PRIMARY KEY` (NOT NULL) | leave-as-is | Defensive coercion only — `int(row["id"])` on a NOT NULL column cannot raise. No change. |
| `dal/bet.py:177` | `casino.__betlog.attrs->'insurance'` (jsonb) | jsonb value, present only when `set_insurance` was called | leave-as-is | Already guarded by `if row and row["insurance"]: return int(...); return 0`. The `if row["insurance"]` is truthy on `None`, `0`, and missing key, so the int cast is safe. No change. |
| `dal/table.py:189` | `casino.__table.minimumbet` | `numeric(10,0) default 100`, nullable | leave-as-is | Already guarded by `int(row["minimumbet"]) if row["minimumbet"] else 0`. The truthy check covers `None` and `0`. No change. |
| `dal/table.py:190` | `casino.__table.maximumbet` | `numeric(10,0) default 100`, nullable | leave-as-is | Same shape as `minimumbet`. No change. |

**Decision criteria:**
- **A (read-site `is not None` check):** column is nullable
  `numeric`, `None` should mean `0`, the existing code path
  has no null guard. Applied at `dal/player.py:92` and
  `dal/bet.py:45`.
- **Leave-as-is:** column is `NOT NULL`, or the column is
  nullable but the existing truthy check (`if row["x"]`)
  already handles `None` correctly.

**Note on `dal/table.py:189-190`:** the existing
`int(row["x"]) if row["x"] else 0` shape is functionally
equivalent to a `is not None` check for `numeric` columns
(`None` and `0` are both falsy). The explicit form is left
in place to avoid a noisy diff; a follow-up could normalize
all three sites to the same shape if desired.

### Phase 2 — schema migration (Option C)

**Cross-repo follow-up.** Landed in `bbsengine6` (or
wherever `engine.__member` is owned), not casino. Tracked
here so the work isn't lost between repos.

**Tasks:**

- [ ] **Cross-consumer audit.** Enumerate every consumer of
  `engine.__member.credits` across the monorepo
  (bbsengine6.bank.account, zoid6, empyre, murdermotel,
  mistermcfeely, casino). For each, confirm the migration
  is safe — i.e. no consumer relies on the column being
  nullable. (The TODO note about empyre's `coins` column
  being intentionally nullable refers to a different
  column; the `credits` column is the one in scope here.)
- [ ] **Write the migration in `bbsengine6/sql/`.** Three
  statements, in this order:
  ```sql
  UPDATE engine.__member SET credits = 0 WHERE credits IS NULL;
  ALTER TABLE engine.__member ALTER COLUMN credits SET DEFAULT 0;
  ALTER TABLE engine.__member ALTER COLUMN credits SET NOT NULL;
  ```
  Order matters: backfill first (cheap), then default
  (no rewrite if PG version is recent enough), then NOT
  NULL (fast because the backfill already cleared all
  NULLs).
- [ ] **Coordinate with the maintainers of the other
  consumers.** At minimum, file an issue in each
  affected repo linking to the migration PR so the
  consumer can adopt the new invariant.
- [ ] **Simplify `get_player_balance` in casino.** Once C
  is deployed, the `is not None` check in
  `dal/player.py:92` becomes dead code. Revert to
  `return int(row["credits"]) if row else 0`. The
  regression test in
  `casino/src/casino/tests/test_player_service.py` stays
  — it now serves as a guard against re-introducing the
  nullable column.
- [ ] **Add a schema-invariant test.** A test that
  queries `information_schema.columns` and asserts
  `engine.__member.credits` has `is_nullable='NO'` and
  `column_default='0'`. Catches the case where the
  casino suite runs against an un-migrated database.

### Cross-references

- `casino/src/casino/dal/player.py:80-92` — the buggy
  `get_player_balance` function.
- `casino/src/casino/services/player.py:51` — the
  `authenticate` call that surfaces the error to clients.
- `bbsengine6/py/src/bbsengine6/bank/account.py` — the
  reference `COALESCE(..., 0)` pattern already in use by
  the bank service.
- `zoid6/TODO.md` "data/bed.json — bank and channel
  modulepaths do not resolve" — bank module resolution is
  already canonical (`bbsengine6.bank.api.handler.BankServiceHandler`,
  registered by `bed.defaultrouter.DefaultRouter`,
  `bed/src/bed/defaultrouter.py:14`). See `bed/SPEC.md:137`.

---

## Rework: route per-hand money through the bank

End state: every money movement in the casino — bets, payouts,
insurance, table-bank credits/debits — flows through
`bbsengine6.bank.api.handler.BankServiceHandler`
(registered by bed's default router, not by casino's
`MessageRouter`; see `bed/SPEC.md:137`) and `bbsengine6.bank`.
The direct `UPDATE engine.__member.credits` writes in
`casino.dal.bet` (lines 54, 150, 201) become bank-mediated
transfers between the member's account and the table's house
account.

### Current design (intentional, captured for context)

The casino maintains **two independent ledgers**:

- **Player's chip stack** — `engine.__member.credits`, the
  per-member wallet. Read by `casino.dal.player.get_player_balance`
  (line 92). Debited on `casino.dal.bet.place_bet` (line 54).
  Credited on `casino.dal.bet.settle_bet` (line 150) and
  `casino.dal.bet.settle_insurance` (line 201). One source of
  truth: the `dal.bet` module.
- **Table bank** — `bank.__account` rows mapped to tables via
  `casino.__bank_table`. Operated at the WS-message layer by
  `bbsengine6.bank.api.handler.BankServiceHandler`
  (registered by `bed.defaultrouter.DefaultRouter`,
  `bed/src/bed/defaultrouter.py:14`; see `bed/SPEC.md:137`)
  and at the maintenance-script layer by
  `casino.services.bank.BankService`. Casino's `MessageRouter`
  does not register a bank service — bank message types are
  loaded by bed, not casino. Covers the orthogonal
  table-bank-management workflow: operator view of the table's
  chip pool, transfers between tables, history audit.

The per-hand money flow (bet → outcome → payout) moves chips
**directly between the member and "in play"**, not through the
table's house account. The two ledgers are intentionally
independent:

- The player's chip stack can go to zero without affecting the
  table's house reserve, and vice versa.
- A double-ledger consistency check is not required for a hand
  to settle. The current design does not require
  `engine.__member.credits` to match any `bank.__account` total.
- Wins and losses are recorded in `casino.__betlog` regardless
  of which ledger the money moves through.

`bbsengine6.bank.api.handler.BankServiceHandler`
(`bbsengine6/py/src/bbsengine6/bank/api/handler.py:83`) covers
`bank_balance`, `bank_add`, `bank_remove`,
`bank_transfer_request`, `bank_transfer_approve`,
`bank_transfer_reject`, `bank_pending`, `bank_history`,
`bank_list_all`, and `stats` — i.e. everything that touches the
table bank rather than the player's chip stack. It is loaded
into the WS server by bed's default router, not by casino's
`MessageRouter` (see `bed/SPEC.md:137`).

### Why the rework

- **Consistent ledger.** Single source of truth for money
  movement; no risk of `engine.__member.credits` drifting
  from `bank.__account` totals.
- **Phase 2 safety.** The `engine.__member.credits`
  `NOT NULL DEFAULT 0` migration (tracked in the
  NULL-credits section's "Phase 2 — schema migration" above)
  becomes safer once the column is a derived view rather
  than the writer of record.
- **Enables real-money features** the current design blocks:
  table transfers during play, cross-table payouts, audit
  reconciliation, chargeback flows.

### Why it's a long-term project

- Requires extending `bbsengine6.bank` to model per-member
  accounts, **or** adding a parallel `bank.__member_account`
  table mapped to `engine.__member`. Schema decision lives in
  `bbsengine6/TODO.md` Phase 7.3.
- Requires a migration of existing `engine.__member.credits`
  values into the new bank account structure, with backfill
  and reconciliation.
- Requires a new transaction-safety layer: every hand must be
  atomic across member-balance, table-balance, and betlog
  (currently `dal.bet` writes three places, not in a single
  transaction; the rework requires one transaction per hand).
- Requires zoid6-side coordination: the unified router's
  bank imports (the "Failed to import bank" warning at
  startup) need to resolve, since the rework makes the bank
  load-bearing rather than operator-only.
- Requires updating the door-mode path
  (`casino.commands.bank`, `casino.services.bank`) and the
  CLI maintenance commands (`casino.maint`) to use the same
  bank-mediated flow.

### Tasks (all unchecked; this is a long-term rework)

- [ ] **Discovery.** Enumerate every writer to
  `engine.__member.credits` in the monorepo. Currently only
  `casino.dal.bet` (lines 54, 150, 201). Add any new writers
  to this audit before the rework begins.
- [ ] **Schema decision.** Per-member accounts in
  `bbsengine6.bank` (extend the existing package) vs a new
  `bank.__member_account` table (parallel structure).
  Cross-references `bbsengine6/TODO.md` Phase 7.3. Decision
  owner: bbsengine6 maintainers.
- [ ] **Migration script.** Backfill existing
  `engine.__member.credits` values into the chosen bank
  structure. Reconcile against any `bank.__account` rows
  already mapped to members.
- [ ] **Transactional `place_bet` / `settle_bet`.** Wrap the
  three writes (member, table, betlog) in a single
  transaction. Fail loud on any error; no partial commits.
  Single transaction per hand.
- [ ] **Bank-mediated `settle_insurance`.** Replace the
  direct `UPDATE engine.__member.credits` in
  `casino.dal.bet.settle_insurance` (line 201) with a
  `LedgerService.credit` call.
- [ ] **Door-mode + CLI update.** Update `casino.commands.bank`
  and `casino.maint` to use the bank-mediated flow.
- [ ] **Phase 2 prerequisite.** The `engine.__member.credits`
  `NOT NULL DEFAULT 0` migration (see NULL-credits section
  above) becomes safe to land only after this rework, since
  the column will be a derived view rather than the writer
  of record.
- [ ] **zoid6 wiring.** Resolve the "Failed to import bank"
  warning at zoid6 startup. The unified router must load the
  bank modulepath, since the bank is now load-bearing for
  all money movement. Cross-references the separate task
  filed in `zoid6/TODO.md` for the modulepath collision.
- [ ] **Cross-repo coordination.** File one-line
  cross-references in `bbsengine6/TODO.md` (schema decision,
  Phase 7.3), `zoid6/TODO.md` (modulepath), `bed/TODO.md`
  (auth balance reads), `mistermcfeely/TODO.md` (postoffice
  / bank account model), `empyre/TODO.md` (note that the
  separate `coins` column is unaffected). [Casino TODO owns
  the task list; cross-refs are one-paragraph pointers in
  the other files.]
- [ ] **Tests.** Replace the per-hand direct-SQL tests in
  `casino/tests/test_slots_integration.py`,
  `casino/tests/test_player_service.py`, and
  `casino/tests/test_yahtzee_service.py` with bank-mediated
  tests. Add a reconciliation test that asserts
  `engine.__member.credits` == `bank.__member_account.balance`
  for a sample of members.

### Cross-references

- `bbsengine6/TODO.md` Phase 7.3 — schema decision for
  per-member bank accounts.
- `zoid6/TODO.md` bank/handler collision entry (line 988)
  and the separate "Failed to import bank" task filed below.
- `empyre/TODO.md` — note that empyre's `coins` column is a
  separate ledger and is unaffected by this rework.
- `casino/dal/bet.py:54,150,201` — the three direct-SQL
  writes this rework will replace.
- `bbsengine6/py/src/bbsengine6/bank/api/handler.py:83` —
  `BankServiceHandler` that the rework will route through.
  Registered by `bed/src/bed/defaultrouter.py:14`; not a
  casino-owned class. See `bed/SPEC.md:137`.

---

## Session plan: post-bring-up cleanup (2026-06-28)

The bed+casino bring-up session on 2026-06-28 discovered
four pre-existing bugs and one missing feature across the
zoid6, bed, and casino repos. The bring-up used a
workaround (the casino side worked around the NULL credits
crash with `UPDATE engine.__member SET credits=1000 WHERE
credits IS NULL`) that is no longer needed once the
fixes land. The NULL-credits crash is already fixed in
`casino/03be20c`; this entry is the index for the
cross-repo work that remains.

This entry is the consolidated session plan and serves as
the index for the per-repo implementation tasks. The
per-repo tasks already exist in the
`## \`_apply_auth_config\` overwrites CLI \`--bed-secret\`
with literal \`~\`` and
`## \`--pidfile\` PID file management` sections in
`bed/TODO.md`, and the
`## \`data/bed.json\` — \`bank\` and \`channel\`
modulepaths do not resolve`,
`## zoid6 unified router: bank modulepath collision`, and
`## \`zoid6.api.handler.MessageRouter\` does not register
\`list_services\`` sections in `zoid6/TODO.md`. Read this
section for the cross-repo picture; read the per-repo
section for the per-repo task list.

### Casino-side work in this session

**One casino TODO edit** lands in Step 4a: the
`## BED (BBS Engine Daemon) Improvements` section item 2
("PID file management - `--pidfile` arg exists but is
never used") is **deleted entirely** (option b in the
session plan). The `--pidfile` arg is owned by the new
`bed` package (`bed/src/bed/lib.py:48-51`); the
casino-side `bed.py` stub is no longer the right home
for tracking it. The
`bed/TODO.md` "## `--pidfile` PID file management" section
is the single source of truth going forward.

**No code change in casino.** This is a doc-only edit.

### Bugs found and status

1. **casino `dal/player.py:92` crashes on `NULL` credits**
   — **FIXED** in `casino/03be20c casino: read NULL credits
   as 0 in get_player_balance and place_bet`. The bring-up
   workaround is no longer needed.

2. **`zoid6/src/zoid6/data/bed.json` `bank` and `channel`
   `modulepath`s do not resolve** — open. Fix path:
   `bank.modulepath` → `bbsengine6.bank.api.handler`;
   `channel.enabled` → `false`. See
   `zoid6/TODO.md` for tasks.

3. **`bed/src/bed/main.py:101` `_apply_auth_config` tilde
   bug** — open. Fix path: wrap the JSON value in
   `os.path.expanduser` at three call sites. See
   `bed/TODO.md` for tasks.

4. **`zoid6/src/zoid6/api/handler.py:13`
   `MessageRouter` does not register `list_services`** —
   open. Fix path: add a `ListServicesService` class,
   register it first in `MessageRouter.register_all`. See
   `zoid6/TODO.md` for tasks.

### Missing feature

5. **`bed` `--pidfile` CLI arg exists but is never
   written** — open. Fix path: write the pidfile at the
   top of `bed/src/bed/main.py:main_async`, remove it in
   a `try/finally` around the autorestart loop. See
   `bed/TODO.md` for tasks.

### Execution plan (7 commits across 4 repos)

When green-lit, the fixes land in this order:

1. **`bed`**: tilde fix.
2. **`zoid6`**: `list_services` handler.
3. **`zoid6`**: bank/channel JSON fix.
4. **`casino`**: delete the superseded `--pidfile` entry
   in the `## BED (BBS Engine Daemon) Improvements`
   section (this file; no code change).
5. **`bed`**: add `## \`--pidfile\` PID file management`
   section to `bed/TODO.md`.
6. **`bed`**: pidfile lifecycle implementation
   (`bed/src/bed/main.py:main_async` write/remove +
   tests + `bed/tests/scripts/stop_bed.sh` +
   `bed/README.md`).
7. **End-to-end verification**: re-run pytest in the
   venv, restart bed with `--pidfile /tmp/bed-test.pid
   --bed-secret /home/opencode/.config/bed/bed.secret`,
   verify pidfile lifecycle, `list_services` returns 56+
   types, no `Failed to import bank` / `Failed to import
   channel` lines, `--bed-secret` honored.

### Pre-execution cleanup (Step 0)

Before any commit lands, four bed processes were racing
on `127.0.0.1:8765` via `SO_REUSEPORT` (pids 3668500,
3797060, 3802229, 3803184). The user's prior approval
covers `kill 3797060 3802229 3803184` (SIGTERM, graceful)
to leave only pid 3668500 (the user's intended instance)
listening. The signal handler at
`bed/src/bed/main.py:370-373` calls
`asyncio.create_task(bed.stop())` on SIGTERM, which
awaits `self.server.stop()` and releases the port.

### Cross-references

- `bed/TODO.md` "## `_apply_auth_config` overwrites CLI
  `--bed-secret` with literal `~`" — per-repo tasks for
  the tilde fix (Step 1).
- `bed/TODO.md` "## `--pidfile` PID file management" —
  per-repo tasks for the pidfile work (Steps 4b-4f).
- `zoid6/TODO.md` "## `data/bed.json` — `bank` and
  `channel` modulepaths do not resolve" — per-repo
  tasks for the JSON fix (Step 3).
- `zoid6/TODO.md` "## zoid6 unified router: bank
  modulepath collision (file as separate task)" — the
  separately-filed bank task (Step 3, option b chosen).
- `zoid6/TODO.md` "## `zoid6.api.handler.MessageRouter`
  does not register `list_services`" — per-repo tasks
  for the handler addition (Step 2).
- `casino/03be20c casino: read NULL credits as 0 in
  get_player_balance and place_bet` — the casino-side
  fix for the NULL credits crash (already landed).

## Casino schema bootstrap fix

Fix for the `relation "casino.__bank_table" does not exist` error
when creating a casino table from the BED-mode casino client
against the production `zoid6` database. Three latent gaps in
`casino.startup.main()`:

- The `citext` extension was never installed by `casino.startup`,
  even though `casino.__player.membermoniker` (and the new
  `__bank_player.membermoniker`) use citext columns. Fresh-DB
  bootstrap crashes on the first table creation.
- Schema-level GRANTs came solely from the inline GRANT in
  `src/casino/sql/schema.sql`. If the schema was created by another
  path (manual psql, `bootstrap_opencode.sql`), privs were never
  re-asserted — non-superuser roles (`web`, `term`, `opencode`) saw
  no `USAGE` on `casino`.
- The 18-entry classlist omitted all 8 bank-related classes added
  in `f978b1e`: `__bank_table`, `bank_table`, `__bank_player`,
  `bank_player`, `__banktransaction`, `banktransaction`,
  `__tabletransfer`, `tabletransfer`.

### Files to edit

- [ ] `git mv casino/scripts/opencode.sql
      casino/scripts/bootstrap_opencode.sql`
- [ ] Edit `casino/src/casino/startup.py:29-79` (`main()`):
  - [ ] Add citext extension block before schema creation
        (`database.extensionavailable` →
        `database.extensioninstalled` → `database.creatextension`,
        hard-fail on missing/inability).
  - [ ] Add schema privs loop after schema creation
        (`database.manage_schema_priv` for
        `sysop=USAGE+CREATE`, `web/term/opencode=USAGE`).
        Hybrid: keeps inline GRANT in `src/casino/sql/schema.sql`.
        Roles assumed to already exist (`bbsengine6.checkroles`).
  - [ ] Expand classlist from 18 → 26 entries in FK-safe order:
    - [ ] Existing 18 (preserve): `__player`/`player`,
          `__table`/`table`, `map_cardtable_player`,
          `__game`/`map_game_player`/`game`,
          `__account`/`account`, `__hand`/`hand`,
          `__betlog`/`betlog`, `__log`/`log`,
          `__slot_spin`/`slot_spin`.
    - [ ] New 8: `__bank_table`/`bank_table` (from
          `bank_table.sql`), `__bank_player`/`bank_player` (from
          `bank_player.sql`), `__banktransaction`/`banktransaction`
          and `__tabletransfer`/`tabletransfer` (from
          `bank_migration.sql`). All four `bank_migration.sql`
          classes FK to `casino.__table(moniker)` — must follow
          `table.sql`.
    - [ ] Migration files (`hidden_table_migration.sql`,
          `table_shoe_migration.sql`) deliberately omitted —
          columns already in `table.sql:14-15,19`.
  - [ ] Add explicit `return failcount == 0` (preserve
        best-effort classlist semantics; extension/priv/schema
        failures still hard-fail via `return False`).
- [ ] Edit `casino/scripts/bootstrap_opencode.sql` (after rename):
  - [ ] Update header comment: new filename, run command
        `psql -d <db> -U postgres -f scripts/bootstrap_opencode.sql`
        from the casino repo root (so `\i 'src/casino/sql/casino.sql'`
        resolves correctly).
  - [ ] Add `CREATE EXTENSION IF NOT EXISTS citext;` before the
        schema bootstrap.
  - [ ] Add `\i 'src/casino/sql/casino.sql'` to load the canonical
        driver (same driver `casino.startup.main` uses via
        `importsql` — one source of truth).
  - [ ] Delete the broken `DO $$ … END $$;` block (old lines
        131‑175) — wrong `__bank_table` schema, missing 7 tables.
  - [ ] Keep verbatim: `ALTER SCHEMA … OWNER TO opencode` and
        table/sequence GRANTs (old lines 5‑66),
        `bank.setup_constraints()` and
        `engine.setup_member_constraints()` SECURITY DEFINER
        helpers (old lines 67‑126), and the
        `casino.__player.stats jsonb` migration (old line 129).
- [ ] Edit `bed/src/bed/startup.py`:
  - [ ] Add `module as bbsmodule` to existing
        `from bbsengine6 import database, io` import line.
  - [ ] Extend `ensure_startup` to dispatch to
        `bbsmodule.runmodule(args, "casino.startup.main")` after
        the bed role setup commits and the conn is released. The
        `"bed startup complete"` status message moves out of the
        `with database.connect(...)` block. `casino.startup.main`
        opens its own pool/conn lifecycle — no shared conn.

### CHANGELOG entries (prepend under `## [Unreleased]` / `## Unreleased`)

- [ ] `casino/CHANGELOG.md`:
  - [ ] `### casino: bring startup.main() up to bbsengine6
        check-module standard` — citext install, schema privs,
        26-entry classlist, hybrid schema GRANT, dropped
        migration files.
  - [ ] `### casino: replace scripts/opencode.sql with
        scripts/bootstrap_opencode.sql` — citext extension, `\i`
        canonical driver, broken `DO $$` block removed, helpers
        and stats migration preserved.
- [ ] `bed/CHANGELOG.md`:
  - [ ] `### bed: ensure_startup also drives casino.startup.main`
        — lazy `bbsengine6.module.runmodule` dispatch, casino
        owns its own pool, idempotent so repeat calls are safe.

### Verification (after execute)

- [ ] `ruff check casino/src/casino/startup.py
        bed/src/bed/startup.py` — clean.
- [ ] `psql -d zoid6test -U postgres -f
        casino/scripts/bootstrap_opencode.sql` — citext
        installed, all 26 classes + opencode GRANTs.
- [ ] `python -m bed.startup --database zoid6test` — bbsengine6 →
        bed role → casino schema, ends with `bed startup complete`.
- [ ] Re-run the BED-mode casino client path that originally
        triggered `relation "casino.__bank_table" does not exist`
        — succeeds.
- [ ] `find casino bed -name __pycache__ -exec rm -rf {} +`
        (per AGENTS.md stale-pyc guard) before re-running tests.
- [ ] `pytest casino/tests/
        bed/src/bed/tests/test_casino_service.py` — all pass
        (especially `test_render_ascii_ends_with_acs_off` per
        AGENTS.md).
- [ ] Idempotency: re-run `python -m bed.startup` against the
        same DB — all classes show `ok` via `classexists`, no
        failures.

---

## Inline menu prompts — one option per line (Done)

**Status:** COMPLETED (commit landed; regression guard in
`tests/test_menu_inline_prompt.py`).

Two `io.inputchoice()` call sites in the WS-client joined the
visible option list with `""`, so the entire menu rendered as a
single horizontal wall of `[T]ables,[C]reate,[U]pdate,...` text
that was hard to scan:

- `src/casino/client/menu.py:menu()` — main casino_client prompt.
  The `inline` join separator is now `"{f6}"` so each option gets
  its own line; status prefix and trailing `casino_client: ` are
  unchanged.
- `src/casino/client/casino_client.py:cmd_bank_menu()` — bank
  submenu. The seven option entries are now `{/all}`-closed with
  `{f6}` between each, putting `[B]alance / [A]dd / [W]ithdraw /
  [T]ransfer / [P]ending / [H]istory / [L]ist all / [Q]uit` on
  separate lines.

Door-mode `mainmenuhelp` (`main.py:88-103`) and the WS-client F1
help callback (`client/menu.py:_render_help`) are unaffected —
both already use one `io.echo()` per option, and `io.echo` appends
`\n` via `end=ECHO_END`. The inline-prompt case is the one that
needs an explicit `{f6}` because the option list is concatenated
before being handed to `io.inputchoice`.

Regression guard:
`tests/test_menu_inline_prompt.py` — pins the seam count
(`len(visible) - 1` `{f6}` markers for the main prompt; 7 for the
bank submenu) and asserts the trailing prompt lands on the last
chunk when the prompt is split on `{f6}`. Spec at
`SPEC.md` §6.1 ("Menu rendering contract (WS-client inline
prompts)").

---

## Test fixture migration: `gen_salt('md5')` → `gen_salt('bf')` (`@since 20260822`)

**Context (2026-08-22, follow-up to the `bbsengine6` password column
hardening).** `bbsengine6/sql/manage_password_format.sql` (new;
`\i`-included from `bbsengine6/sql/bbsengine6.sql` after `member.sql`)
adds `chk_member_password_bcrypt` on `engine.__member.password`:

    check (password is null or password ~ '^\$2[abxy]\$')

The constraint rejects **any** non-NULL, non-bcrypt write — including
the `$1$` MD5-crypt hashes that nine casino test files currently
seed via `crypt('test', gen_salt('md5'))`. Once the constraint is
applied to a live DB (via `bbsengine6` `make schema-init` or a fresh
`psql -f bbsengine6.sql` against the test DB), every one of these
fixtures fails with a CHECK-violation error and the test suite is
wedged.

**Files affected (9):**

```
casino/src/casino/sql/test_data.sql
casino/src/casino/tests/test_blackjack_flow.py:215-216
casino/src/casino/tests/test_blackjack_three_hands.py:130-140
casino/src/casino/tests/test_member_services.py:54
casino/src/casino/tests/test_new_features_integration.py:78-79
casino/src/casino/tests/test_player_observer.py:207-217
casino/src/casino/tests/test_player_stats_integration.py:48-49
casino/src/casino/tests/test_slots_integration.py:47,574-575
```

(The `test_data.sql` line for `__dealer__` uses
`crypt('__no_password__', gen_salt('md5'))` — same prefix issue.)

### [ ] Migrate every `crypt(?, gen_salt('md5'))` to `crypt(?, gen_salt('bf'))`

Mechanical substitution; no semantic change to the seed plaintexts
(`'test'`, `'x'`, `'__no_password__'`). Each fixture currently asserts
the seeded user can `auth login` with that plaintext; the round-trip
is the same once the algorithm is bcrypt — `crypt('test', stored)`
still returns `stored` because bcrypt uses the stored `$2b$` prefix
to select the algorithm.

Two notes on the migration shape:

1. The plaintext `'__no_password__'` for `__dealer__` is a sentinel,
   not a real password. Bcrypt's `$2b$` output is still 60 chars and
   the round-trip still works — `crypt('__no_password__', stored)`
   returns `stored` if and only if `stored` was hashed from
   `'__no_password__'`. No code change to the sentinel; just the
   `gen_salt` argument.

2. The 9 fixtures use `crypt(?, gen_salt('bf'))` as the literal
   embedded in the SQL string, not a parameter — i.e.
   `crypt('test', gen_salt('bf'))` rather than `crypt(%s,
   gen_salt('bf'))` with `(plaintext,)` as params. The substitution
   is purely literal. **Do not** migrate these to bound parameters
   in the same commit; that's a separate cleanup (and `checkpassword`
   already binds the plaintext via `%s` per the `member auth hot
   path` TODO entry).

Resolution: zero `gen_salt('md5')` matches in `casino/`. Pin a
regression test in `tests/test_password_algorithm_no_md5.py` (new)
that greps the entire `casino/` tree for `gen_salt('md5')` and
asserts zero matches. The grep must exclude vendored code (none
today, but if `casino/vendor/` ever grows, add `--exclude-dir=vendor`).

Verification:

- [ ] `grep -rn "gen_salt('md5')" casino/src casino/tests` returns
      zero matches.
- [ ] `tests/test_blackjack_flow.py`, `test_blackjack_three_hands.py`,
      `test_slots_integration.py`, and the rest still pass against a
      DB with `chk_member_password_bcrypt` applied.
- [ ] `tests/test_password_algorithm_no_md5.py` passes (the
      operator signal that no fixture is left behind).
- [ ] Live casino test DB (`zoid6`) has the constraint applied
      (run `bbsengine6/sql/bbsengine6.sql` against it once; the
      constraint creation is idempotent via `DROP CONSTRAINT IF EXISTS`
      + `ADD CONSTRAINT`).

Cross-ref: `bbsengine6/TODO.md` (line 35 cross-ref notes this casino
TODO is the operator-facing follow-up to the schema-side CHECK
constraint), `zoid6/TODO.md` "Password column hardening — legacy
MD5-crypt migration (@since 20260822)" (the parent incident), and
`bbsengine6/CHANGELOG.md` "[Unreleased] member + sql: password
column hardening" (the constraint that triggers this entry).

