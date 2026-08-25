# casino — Specification

> **Last updated:** 2026-08-21.
> **Status:** Alpha (`Development Status :: 3 - Alpha`); production
> wiring (MessageRouter + CasinoSessionManager + bed-native auth)
> in place; games are feature-complete per their READMEs.

> **Note**: See [`TODO.md`](./TODO.md) for a list of unimplemented
> features and future work.

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [Architecture](#2-architecture)
3. [Layered package layout](#3-layered-package-layout)
4. [WebSocket services](#4-websocket-services)
5. [Door-mode BBS module](#5-door-mode-bbs-module)
6. [Standalone TUI client](#6-standalone-tui-client)
7. [Poker variant plugin system](#7-poker-variant-plugin-system)
8. [SQL schema](#8-sql-schema)
9. [Per-table stats & duplicate-table short-circuit](#9-per-table-stats--duplicate-table-short-circuit)
10. [Configuration](#10-configuration)
11. [Cross-reference map](#11-cross-reference-map)
12. [Authoritative file index](#12-authoritative-file-index)
13. [Out of scope](#13-out-of-scope)

---

## 1. Purpose & Scope

`casino` is a Python package that ships five casino-style games
(blackjack, slots, poker, yahtzee, tic-tac-toe) on top of
[bbsengine6](../bbsengine6/). It exposes three run modes:

1. **Door-mode BBS module** — registered with bbsengine6, interactive
   ttyio menu in a BBS session.
2. **WebSocket game server** — registered with bed via
   `casino.api.handler.MessageRouter`.
3. **Standalone TUI client** — long-lived WebSocket client for
   sysops and CI.

It does **not** own:

- Authentication wire-protocol (bed's `AuthService` does).
- Daemon lifecycle (bed does).
- Per-member PostgreSQL role provisioning
  (`bbsengine6.pgrole` does).
- The bank ledger (casino wraps `bbsengine6.bank`, but the ledger
  lives in bbsengine6).

## 2. Architecture

```
                ┌──────────────────────────────────────────────┐
                │ casino  (Python package)                    │
                │                                              │
                │   ┌── MessageRouter  ◄─── bed --router      │
                │   │     (api/handler.py:904)                 │
                │   │     registers all 7+ services            │
                │   │     + CasinoSessionManager               │
                │   ▼                                          │
                │   AuthService        ─► bbsengine6.member    │
                │   TableServiceHandler                        │
                │   GameServiceHandler                        │
                │   BetServiceHandler                         │
                │   ChatServiceHandler                        │
                │   BankServiceHandler (bed defaultrouter)      │
                │   ─► bbsengine6.bank                         │
                │   PokerServiceHandler ─► poker.*             │
                │   Yahtzee / TicTacToe / PostOffice handlers │
                │                                              │
                │   ┌── DAL  ◄─── async (aiosql) + sync        │
                │   ▼                                          │
                │   services/  (game, poker, slots, …)         │
                │                                              │
                │   sql/   (casino.* schema)                   │
                └──────────────────────────────────────────────┘
                       ▲                          ▲
                       │ (door-mode)              │ (TUI client)
                       │                          │
┌──────┴─────────┐         ┌──────┴─────────┐
                 │ main.py menu   │         │ CasinoClient   │
                 │ --direct flag  │         │ default branch │
                 │ bbsengine6 BBS │         │ ws://bed:8765/ │
                 └────────────────┘         └────────────────┘
```

### 2.1 Member vs casino player

Casino has its own auth (`PlayerService.authenticate`,
`AuthService._handle_auth`) on top of the BBS member layer
(`bbsengine6.member`) so many concurrent BBS members can play casino at
once, each with their own 1:1 casino player record. Two distinct rows
back each casino user:

| Identity | Table | Created by | Holds |
|---|---|---|---|
| **Member** | `engine.__member` | Sysop via `bbsengine6-console` (interactive `console.member.add`) | BBS-level credentials (`moniker`, `password`), global `credits`, flags (`SYSOP`, `APPROVED`), email |
| **Casino player** | `casino.__player` | Lazily, on first casino touch — see below | Casino-specific state: `lastplayed`, `attrs`, `stats` (per-game counters: wins / losses / net / `blackjack.blackjacks` / `slots.biggest_win` / …) |

The casino player row has `membermoniker citext` with a FK to
`engine.__member(moniker)` (`casino/src/casino/sql/player.sql`), so the
relationship is **1:1 by membermoniker** — every casino player has
exactly one BBS member, and every BBS member has at most one casino
player. "Many players" means many BBS members running casino clients
concurrently, not multiple casino rows per member. The 1:1 shape is
preserved across the whole stack; no schema migration is required to
add casino users.

**Lifecycle (lazy, audit-on-create).** The casino player row is
materialized by a single helper,
`casino.services.player.ensure_casino_player(args, moniker, *, audit)`,
called from both entry paths:

- WS-client auth: `PlayerService.authenticate` calls
  `ensure_casino_player(audit=False)` on every successful login so the
  wire stays clean even on the first login.
- Door-mode facade: `lib.CasinoPlayer.__init__` calls
  `ensure_casino_player(audit=True)` so the bottombar (`_casino_credits_fragment`),
  stats menu (`casino.menu.show_player_stats`), and table-seat filter
  (`_refresh_seat`) see real values from the first frame.
- When `audit=True` and a row is newly created, one `io.echo(..., level="debug")`
  fires with the membermoniker so a sysop running `casino --debug` can
  audit who was auto-materialized. Subsequent constructions for the
  same member are silent.

There is **no** explicit `casino init <moniker>` step in v1 — the
audit echo is the sysop's window into "who got auto-created." A
follow-up could add an explicit init command if operators want
finer-grained control.


## 3. Layered package layout

`casino` follows a four-layer architecture:

| Layer         | Module                     | Role                                    |
|---------------|----------------------------|-----------------------------------------|
| **Transport** | `api/handler.py`           | MessageRouter, CasinoSessionManager, all WebSocket services |
|               | `api/messages.py`          | MessageType enum + dataclasses          |
| **Service**   | `services/game.py`         | Blackjack game logic                    |
|               | `services/poker.py`        | Poker betting state machine             |
|               | `services/slots.py`        | Atomic spin transactions                |
|               | `services/bank.py`         | Wraps `bbsengine6.bank` for casino:house |
|               | `services/player.py`       | Auth via `bbsengine6.member`            |
|               | `services/table.py`        | Table CRUD                              |
| **DAL**       | `dal/bet.py game.py player.py slots.py table.py` | Sync DAL |
|               | `dal/aiosql/*`             | Async DAL                               |
| **Domain**    | `games/base.py`            | GameType / GameAction enums + BaseGame  |
|               | `cards/__init__.py`        | Card dataclass + png loader             |
|               | `poker/lib.py`             | HandRank, BettingStructure, PokerDeck   |
|               | `blackjack/hand.py`        | Hand dataclass                          |
|               | `tictactoe/lib.py`         | Board, AI, scoring                      |
|               | `yahtzee/lib.py`           | Scoring + rake math                     |

## 4. WebSocket services

`casino.api.handler.MessageRouter` registers every service with the
bed WebSocket server. The full surface:

| Service                 | Message types                                                                                     |
|-------------------------|---------------------------------------------------------------------------------------------------|
| `AuthService`           | `auth`, `ping`                                                                                    |
| `TableServiceHandler`   | `list_tables`, `create_table`, `update_table`, `join_table`, `leave_table`, `watch_table`, `stop_watching` |
| `GameServiceHandler`    | `hit`, `stand`, `double`, `split`                                                                  |
| `BetServiceHandler`     | `bet`                                                                                             |
| `ChatServiceHandler`    | `chat_table`, `chat_global`, `emote`                                                              |
| `BankServiceHandler` *(bed; from `bbsengine6.bank.api.handler`)* | `bank_balance`, `bank_add`, `bank_remove`, `bank_transfer_request`, `bank_transfer_approve`, `bank_transfer_reject`, `bank_pending`, `bank_history`, `bank_list_all` |
| `PokerServiceHandler`   | `poker_create_table`, `poker_join_table`, `poker_leave_table`, `poker_start_hand`, `poker_action`, `poker_fold`, `poker_check`, `poker_call`, `poker_bet`, `poker_raise`, `poker_all_in`, `poker_get_state`, `poker_list_tables` |
| `YahtzeeService`        | (per-game — see `yahtzee/README.md`)                                                              |
| `TicTacToeService`      | (per-game — see `tictactoe/README.md`)                                                            |
| `PostOfficeService`     | IMAP polling, notification fan-out                                                                |

Bank service is loaded by `bed.defaultrouter.DefaultRouter.register_all`
(`bed/src/bed/defaultrouter.py:14`); not registered by
`casino.api.handler.MessageRouter`. See `bed/SPEC.md:137`.

The `CasinoSessionManager` (subclass of `bbsengine6.session.SessionManager`)
handles per-websocket session state, including the bottombar fragment
registry per package (`bottombar.registry_for('casino')`).

Services register on a last-write-wins basis
(`bbsengine6.net.transport.register_service`), so when casino is the
fronting router its `AuthService` (registered for `auth`) supersedes
bed's native AuthService. Casino therefore owns its own auth flow
because it must not depend on bed; the shared credential primitives
live in `bbsengine6.member`, not in the daemon.

`bbsengine6.member.verifyMemberFound` follows the
**CONN_POOL_PATTERN**: the caller must supply a `pool=`.
`PlayerService` resolves the pool once per `authenticate` call via
`PlayerService._pool()`, which:

1. reuses `args.pool` when the daemon has set one at startup, otherwise
2. falls back to the cached `database.getpool(args, database=...)`.

The resolved pool is threaded through `verifyMemberFound`,
`has_password`, and `checkpassword` so a single borrowed connection
backs the whole credential check. Omitting the pool triggers
`bbsengine6.member._verify_member.100: pool is required`.

## 5. Door-mode BBS module

The door-mode entry is `python -m casino` (`__main__.py`). It:

1. Runs `bbsengine6.startup` to verify the database schema.
2. Opens a BBS session (`bbsengine6.session.SessionRegistry`).
3. Enters `main.py:main`, a ttyio-based menu offering:
   - Blackjack
   - Poker
   - Slots
   - Connect-to-BED
   - Table list / join / view
   - Watch / unwatch tables
   - Bet / hit / stand
   - Global chat
   - Bank
   - Maintenance (sysop only)

## 6. Standalone TUI client (merged `casino` default branch)

The merged `casino` CLI is the standalone entry. It exposes the same
bed-style flag set as every other tool under `bed.tools`
(`--bed-host`, `--bed-port`, `--bed-path`, `--bed-call-timeout`,
`--bed-probe-timeout`, plus `--direct` to opt out of the daemon).

Default branch: bed WebSocket client. `casino.__main__:main` probes
the bed daemon on the configured `--bed-host`/`--bed-port`; if
reachable, instantiates `CasinoClient`
(`src/casino/client/casino_client.py`) and runs the terminal UI
loop. If unreachable and `--direct` was not passed, raises
`bed.tools._routing.BedNotReachable` and exits non-zero with the
bundled "rerun with --direct" hint.

`--direct` branch: door mode. Opens a Postgres connection pool via
`bbsengine6.database`, starts a BBS session, runs `casino.main` —
the interactive menu. Mirrors the pre-merge `casino` shim's behavior.

`CasinoClient` authenticates with the BED server and exposes table
management, blackjack, poker, tic-tac-toe, chat, and bank operations
from the command line. Auth always prompts for password (commit
`ec0138e`) and reports a specific failure reason (`Member not found`,
`Invalid moniker`, `Authentication service unavailable`).

The legacy `casino-client` shell shim and console-script entry point
were removed; `python -m casino.client_cli` still works for callers
that imported the entry point directly.

### 6.1 Menu rendering contract (WS-client inline prompts)

Two prompts in the WS-client put the visible option list **inline**
on the same terminal line as the status prefix — these are the only
spots in the casino that join multiple `[X]label` fragments into a
single `io.inputchoice(...)` prompt string:

1. `src/casino/client/menu.py:menu()` — the main casino_client
   prompt. `status` (`[moniker] Balance: X [Table: Y]`) is followed
   by the visible options, then the final `casino_client: ` prompt.
2. `src/casino/client/casino_client.py:cmd_bank_menu()` — the bank
   submenu prompt.

Both prompts must put **one `{f6}` between every adjacent option
entry**, plus **one `{f6}` after the status prefix** (so the
balance lands on its own line) and **one `{f6}` before the
trailing prompt** (so `casino_client: ` lands on its own line).
Net: `len(visible) + 1` `{f6}` markers in the main prompt, and
`len(visible) - 1` in the bank submenu (the bank submenu prompt
does not prepend a status line). The pre-fix behavior was
`"".join(...)` / `"…{/all}{var:optioncolor}[A]…"`, which rendered
the entire option list as one continuous horizontal string
(`[T]ables,[C]reate,[U]pdate,...`) and was hard to read. The
contract is now: each option gets its own line, the status
prefix (balance) sits on the line above the first option, and
the trailing `casino_client: ` / `: ` sits on the line below the
last option.

In addition, every option dispatch site in the WS-client loop
(`CasinoClient.run` for the main menu, `cmd_bank_menu` for the
bank submenu) emits a one-line `io.echo("Label")` immediately
before invoking the handler, so the operator sees what action
was just selected before the handler's output (e.g. `io.echo("Bank")`
fires before `cmd_bank_menu()` runs). `[Q]uit` does not emit a
label since it breaks the loop without invoking a handler.

The F1 help callback (`_render_help`, `client/menu.py:55-69`) and
the door-mode `mainmenuhelp` (`main.py:88-103`) are not affected —
both already use one `io.echo()` per option, and `io.echo` appends
`\n` via `end=ECHO_END`, so each option naturally lands on its
own line. The inline-prompt case is the one that needs an explicit
`{f6}` because the option list is concatenated before being handed
to `io.inputchoice`.

### 6.2 Tabular screen rendering contract (width + locale)

Every tabular screen in `CasinoClient.handle_message`
(`table_list`, `bank_pending`, `bank_history`, `bank_list_all`,
`slot_paytable`, `slot_history`, `slot_table_history`) routes
through `casino.client.table_render.render_table`. The contract:

- The block uses the available terminal width, computed as
  `io.terminal.width() - 2` (mirrors `bbsengine6.util.hr`'s
  `HR_WIDTH_OFFSET`). Column widths are allocated from that
  budget, with per-column floors of 4 characters. Variable-
  width columns share leftover space pro-rata and are truncated
  with a trailing `…` when content overflows the allocated slot.
- Numeric columns are right-aligned and rendered through
  `_safe_int_str` / `_signed_str`, which call `f"{n:n}"` for
  locale-aware thousands separators (`1,234,567` under
  `en_US`, `1234567` under `C`). If the active locale's
  separator is non-ASCII (NBSP under `fr_FR`), the helper
  falls back to `str(int(n))` so column alignment never
  drifts.
- The header and each row are returned as separate strings
  carrying `{var:labelcolor}` / `{var:valuecolor}` /
  `{boxcolor}` bbsengine6 tags; the caller iterates and emits
  one `io.echo(line)` per string so the echo pipeline appends
  `ECHO_END` per line (see AGENTS.md, "f-string markup" note).
- Locale is initialized once on the WS-client path via
  `locale.setlocale(LC_ALL, "")` in `_run_bed`
  (`casino/__main__.py`), matching the `_run_direct` and
  `_run_blackjack` branches. The empty-string form is a no-op
  when locale is already set.

Tests pin these contracts in
`casino/tests/test_client_table_render.py`.

## 7. Poker variant plugin system

Poker variants are registered via setuptools entry points under the
`casino.poker.variants` group (`pyproject.toml`):

| Variant         | Entry point                            | Class                |
|-----------------|----------------------------------------|----------------------|
| Texas Hold'em   | `casino.poker.variant.texas_hold_em`    | `TexasHoldEm`        |
| Omaha           | `casino.poker.variant.omaha`            | `Omaha`              |
| Omaha Hi-Lo     | `casino.poker.variant.omaha`            | `OmahaHiLo`          |
| 7-Card Stud     | `casino.poker.variant.seven_card_stud`  | `SevenCardStud`      |

`casino.poker.variant.VariantRegistry` discovers them at import time
via `importlib.metadata.entry_points()`. New variants are added by
subclassing `BaseVariant` and registering a new entry point — no
core change required.

### Betting streets

- Texas Hold'em / Omaha: preflop → flop → turn → river
- 7-Card Stud: third_street → fourth_street → fifth_street →
  sixth_street → seventh_street

### Hand rankings

All poker hands are evaluated from Royal Flush (highest) to High Card
(lowest): Royal Flush, Straight Flush, Four of a Kind, Full House,
Flush, Straight, Three of a Kind, Two Pair, Pair, High Card.

### Key classes (in `poker/`)

| Class              | File                          | Role                                |
|--------------------|-------------------------------|-------------------------------------|
| `PokerDeck`        | `poker/lib.py`                | Deck management                     |
| `PokerCard`        | `poker/lib.py`                | Card dataclass                      |
| `HandRank`         | `poker/lib.py`                | Hand rank + tie-breaker             |
| `BettingStructure` | `poker/lib.py`                | No-Limit / Pot-Limit / Fixed-Limit  |
| `PokerDealer`      | `poker/dealer.py`             | Shuffle / deal / burn / reset       |
| `PokerPlayer`      | `poker/player.py`             | Player state + action validation    |
| `PokerService`     | `services/poker.py`           | Betting state machine + showdown     |

## 8. SQL schema

Two schema locations exist:

- `src/casino/sql/` (~30 files) — current canonical schema, loaded
  by `startup/main.py` at bring-up. Includes `schema.sql`, `account`,
  `account_view`, `bank_migration`, `bank_player`, `bank_table`,
  `betlog`, `betlog_view`, `casino.sql` (legacy), `game`,
  `game_view`, `hand`, `hand_view`, `hidden_table_migration`,
  `log`, `log_view`, `map_cardtable_player`, `map_game_player`,
  `player`, `player_view`, `slot_spin_view`, `slots`, `table_shoe_migration`,
  `table`, `table_view`, `test_data`.
- `scripts/poker.sql` — older poker-only migration set with
  `casino.__poker_table`, `casino.__poker_hand`,
  `casino.__poker_player_hand`, `casino.__poker_bet`,
  `casino.__poker_pot`, `casino.__poker_seat`,
  `casino.__poker_stats`. Superseded by the current
  `src/casino/sql/` schema for production use; kept for historical
  reference.
- `zoidweb2-casino.sql` — orphaned Dec-2025 snapshot. **Do not
  use.**

### 8.1 Startup module

Casino ships a dedicated startup subpackage at `src/casino/startup/`
that runs after `bbsengine6.startup` completes. The subpackage
performs the casino-specific bootstrap work that depends on the
`bbsengine6` trust model landing in `stage_one`:

1. **Extension install** — `citext` is required by
   `casino.__player.membermoniker` and `casino.__bank_player`.
   Fresh-DB bootstrap crashes on the first table creation
   without it.
2. **Schema ownership** (`startup/checkcasino.py`) — ensures
   the `casino` schema is owned by the dedicated `zoid6`
   PostgreSQL role (`NOSUPERUSER NOCREATEDB NOCREATEROLE
   NOLOGIN INHERIT`). Mirrors the engine schema block in
   `bbsengine6.backend.checkengine` and the bank schema block
   in `bbsengine6.backend.checkbank`. Required because the
   SECURITY DEFINER helper `public.manage_schema_priv` (also
   owned by `zoid6`) issues the per-role `GRANT USAGE ON
   SCHEMA casino TO ...` statements in step 4 below; under
   NOSUPERUSER, the helper can only `GRANT` on objects it owns,
   so the schema must be `zoid6`-owned or every grant in the
   loop fails with `permission denied for schema casino`.
   The module also verifies the owner of each of the 5
   `public.*` SECURITY DEFINER helpers against the canonical
   allow-list `("zoid6", "postgres")` before calling any of
   them (mirrors `bbsengine6.backend.checkengine`'s owner
   gate). Idempotent: re-run on an already-`zoid6`-owned
   schema is a no-op.
3. **Schema import** — `casino.sql.schema.sql` runs, creating
   the `casino` schema and issuing inline `GRANT USAGE` to
   `sysop`, `web`, `term`, `opencode`.
4. **Schema privs** — re-asserts `manage_schema_priv("grant",
   "usage", "casino", <role>)` for `web`, `term`, `sysop`,
   `opencode` and `manage_schema_priv("grant", "create",
   "casino", "sysop")`. Re-issuing here means privs survive
   any path that may have skipped `schema.sql`'s inline
   grants (manual psql, `bootstrap_zoid6.sql`, etc.).
5. **Class import** — 26 entries in FK resolution order.
   Migration files (`hidden_table_migration.sql`,
   `table_shoe_migration.sql`) are deliberately omitted; their
   columns are already in `table.sql`.

The startup subpackage follows the bbsengine6 BBS-module
convention (`init`, `access`, `buildargs`, `main`) so it can be
invoked via `module.run` from the unified router. See
`bbsengine6/SPEC.md` §5 ("Cross-module schema ownership") for
the broader pattern and `bbsengine6/TODO_zoid6_role.md` §4
("Cross-module schema ownership pattern") for the canonical
reference and open follow-ups.

## 9. Per-table stats & duplicate-table short-circuit

### `create_table` short-circuit (owner-or-sysop)

When `Moniker.create_table` is invoked with a moniker that is already
taken by a table of the **same** game type, the second call no longer
fails with a generic `create_failed` error. Instead:

1. `dal.table.create_table` (sync + aiosql) pre-checks
   `casino.__table` for an existing row and returns a sentinel dict
   shaped like the normal table row but with ``"__exists__": True``.
2. `services.table.TableService.create_table` strips the sentinel
   key and returns ``{"success": False, "exists": True, "table":
   existing_dict, "message": …}``.
3. `api.handler.TableServiceHandler._handle_create_table` routes the
   ``exists`` branch to a new ``table_exists`` envelope, gated by an
   owner-or-sysop check:

   - **Owner of the existing table** (case-insensitive moniker
     match): receives the full payload + stats.
   - **Sysop** (`state.is_sysop == True`): same payload, used to
     inspect hidden tables owned by other monikers.
   - **Anyone else**: receives ``type="error", code="create_failed"``,
     indistinguishable from any other create failure so the existence
     of the table is not leaked.

A duplicate moniker with a **different** game type surfaces as
``type="error", code="type_mismatch"`` so callers do not silently
bind a yahtzee table to a blackjack moniker.

### `table_exists` wire payload

```json
{
  "type": "table_exists",
  "moniker": "blackjack-jam",
  "game_type": "blackjack",
  "owner": "jam",
  "min_bet": 10,
  "max_bet": 1000,
  "location": "NorthAlpha",
  "hidden": false,
  "stats": { ... per-table aggregate ... },
  "message": "blackjack table 'blackjack-jam' already exists; showing stats"
}
```

The client (`src/casino/client/casino_client.py`, `table_exists`
branch in `handle_message`) renders this with the
`{var:labelcolor}` / `{var:valuecolor}` label/value pattern
established at `yahtzee/play.py:176-253`.

### Per-table stats shape (game-type aware)

`dal.table.get_table_stats(args, moniker, game_type, surrender_multiplier=0.5)`
returns a dict keyed by `game_type`:

| Game type  | Shape                                                            |
|------------|------------------------------------------------------------------|
| `blackjack` | `{hands_played, wins, losses, pushes, blackjacks, busts, surrenders, net}` |
| `slots`    | `{spins, wins, losses, net}`                                     |
| `yahtzee`  | `{hands_played, wins, losses, draws, net}`                       |
| `tictactoe`| `{hands_played, wins, losses, draws, net}`                       |
| `poker`    | `{}` (poker is in-memory; nothing to aggregate yet — see §11)    |

The blackjack `net` honors the configured `surrender_multiplier`
(§10) so per-table net stays consistent with what the settle path
actually credited the player.

Stats are sourced from `casino.__game` for blackjack / yahtzee /
tictactoe and from `casino.__slot_spin` for slots. Settle paths
write `attrs->'outcome'`, `attrs->'bet_amount'`, and (for
yahtzee/tictactoe) `attrs->'net'` on the `__game` row via the new
`dal.game.update_game_attrs` (sync + aiosql) merge helper.

### Sysop hidden-table visibility

A sysop issuing `create_table` with a moniker that is already a
**hidden** table owned by another player receives the `table_exists`
payload. The hidden-flag is preserved in the response so a sysop
audit client can distinguish hidden from public tables in the
display layer. The pre-check is done with a real measurement
(`SELECT … FROM casino.__table`) — no in-memory guesswork.

## 10. Configuration

The casino config block is sourced from `bed.json` under the
`casino` key (per-casino nested layout):

```json
{
  "casino": {
    "blackjack": {
      "surrender_allowed": "early",
      "surrender_multiplier": 0.5
    }
  }
}
```

Helpers in `src/casino/config.py`:

| Function                       | Purpose                                                                                  |
|--------------------------------|------------------------------------------------------------------------------------------|
| `load_config()`                | Read JSON / merge env (canonical casino config loader; unchanged)                        |
| `get_postoffice_config()`      | Existing postoffice block helper                                                          |
| `get_casino_config(args)`      | Return the casino-level block: prefers `args._casino_config` (wired by bed), falls back to `args._casino_config_file`, then `{}`. |
| `get_surrender_multiplier(args)` | Read `casino.blackjack.surrender_multiplier`, defaulting to `0.5`. Honors `surrender_allowed` (`False` / `"none"` → `0.0`); clamps out-of-range and garbage values to the `0.5` default. |

`MessageRouter.__init__` calls `_bootstrap_casino_config(args)`,
which auto-discovers the `casino` section from `args.config_file`
when bed has not wired it explicitly. This keeps door-mode and
standalone tests working with the `0.5` default without requiring
a bed wiring change. When bed later wires the section explicitly
(planned), the auto-discovery short-circuits on the wired value.

## 11. Cross-reference map

| Concept                            | File                                          |
|------------------------------------|-----------------------------------------------|
| MessageRouter                      | `src/casino/api/handler.py`                   |
| Message types                      | `src/casino/api/messages.py`                  |
| Door-mode menu                     | `src/casino/main.py`                          |
| Door-mode entry                    | `src/casino/__main__.py`                      |
| Standalone client                  | `src/casino/client/casino_client.py`          |
| Client auth                        | `src/casino/auth.py`                          |
| Card / Hand / Shoe                 | `src/casino/lib.py`                           |
| Blackjack game logic               | `src/casino/services/game.py`                 |
| Poker state machine                | `src/casino/services/poker.py`                |
| Slots                              | `src/casino/services/slots.py`                |
| Bank wrapper                       | `src/casino/services/bank.py`                 |
| Player auth                        | `src/casino/services/player.py`               |
| Table CRUD                         | `src/casino/services/table.py`                |
| `__exists__` sentinel / stats      | `src/casino/dal/table.py` (+ `dal/aiosql/table.py`) |
| Outcome-attr writes                | `src/casino/dal/game.py` (`update_game_attrs`) |
| Bed.json casino helpers            | `src/casino/config.py` (`get_casino_config`, `get_surrender_multiplier`) |
| Backend selector                   | `src/casino/_routing.py`                      |
| DAL (sync)                         | `src/casino/dal/{bet,game,player,slots,table}.py` |
| DAL (async / aiosql)               | `src/casino/dal/aiosql/*`                     |
| Games registry                     | `src/casino/games/base.py`                    |
| Card resource loader               | `src/casino/cards/__init__.py`                |
| Poker evaluator                    | `src/casino/poker/lib.py`                     |
| Poker variants                     | `src/casino/poker/variant/*`                  |
| Tic-tac-toe protocol               | `src/casino/tictactoe/README.md`              |
| Tic-tac-toe engine                 | `src/casino/tictactoe/{api_handler,dealer,lib,service}.py` |
| Yahtzee protocol                   | `src/casino/yahtzee/README.md`                |
| Yahtzee engine                     | `src/casino/yahtzee/{api_handler,dealer,lib,service}.py` |
| Slots door                         | `src/casino/slots/{__main__,dealer,game,lib,play,player}.py` |
| Sysop maintenance                  | `src/casino/maint/__main__.py`                |
| Per-game BBS commands              | `src/casino/commands/{admin,bank,chat,game,poker,table}/` |
| Schema (current)                   | `src/casino/sql/`                             |
| Schema (poker legacy)              | `scripts/poker.sql`                           |
| Per-host landing page              | `www/php/index.php` + `www/skin/{scss,tmpl}/` |
| Console-script manifest            | `pyproject.toml`                              |

## 12. Authoritative file index

| Path                                              | Role                                  |
|---------------------------------------------------|---------------------------------------|
| `pyproject.toml`                                  | Manifest (1 console script + 4 poker variants) |
| `src/casino/__init__.py`                          | Package init (BBS module entry)      |
| `src/casino/__main__.py`                          | `python -m casino` entry              |
| `src/casino/main.py`                              | Door-mode menu                        |
| `src/casino/auth.py`                              | BED auth + BBS entry                  |
| `src/casino/lib.py`                               | Card / Hand / Shoe / CasinoPlayer + bottombar |
| `src/casino/config.py`                            | Env-var config loader + bed.json `casino` block helpers (`get_casino_config`, `get_surrender_multiplier`) |
| `src/casino/client_cli.py`                        | legacy `python -m casino.client_cli` entry |
| `src/casino/_routing.py`                          | bed / direct backend selector         |
| `src/casino/startup/`                             | Casino-specific bootstrap subpackage (extension install + schema ownership + schema.sql import + class import) |
| `src/casino/startup/main.py`                      | Orchestrates citext install, `checkcasino`, schema.sql, `manage_schema_priv` grants, and class imports |
| `src/casino/startup/checkcasino.py`               | Mirrors `bbsengine6.backend.checkengine`/`checkbank`'s schema-ownership block for the `casino` schema; verifies the 5 SECURITY DEFINER helper owners against the `("zoid6", "postgres")` allow-list |
| `src/casino/api/handler.py`                       | MessageRouter + CasinoSessionManager + services |
| `src/casino/api/messages.py`                      | MessageType enum + dataclasses        |
| `src/casino/services/{bank,game,player,poker,slots,table}.py` | Business logic              |
| `src/casino/dal/*` + `dal/aiosql/*`               | Data access                           |
| `src/casino/games/base.py`                        | GameType / GameAction enums + BaseGame |
| `src/casino/cards/__init__.py`                    | Card dataclass + png loader           |
| `src/casino/poker/lib.py`                         | HandRank, BettingStructure, PokerDeck |
| `src/casino/poker/variant/{base,evaluator,texas_hold_em,omaha,seven_card_stud}.py` | Poker variants |
| `src/casino/tictactoe/{api_handler,dealer,lib,service}.py` | Tic-tac-toe                  |
| `src/casino/yahtzee/{api_handler,dealer,lib,service}.py`   | Yahtzee                      |
| `src/casino/slots/{__main__,dealer,game,lib,play,player}.py` | Slots                       |
| `src/casino/blackjack/{game,hand,lib,play}.py`    | Blackjack                             |
| `src/casino/maint/__main__.py`                    | Sysop maintenance menu                |
| `src/casino/commands/{admin,bank,chat,game,poker,table}/` | BBS CLI subcommands         |
| `src/casino/sql/`                                 | Current canonical schema              |
| `src/casino/tests/`                               | pytest (~50 modules)                  |
| `src/casino/tests/test_blackjack_three_hands.py`  | Self-contained WS auth + create + join + 3 hands + duplicate-table scenario |
| `src/casino/tests/test_blackjack_three_hands_bed.py` | Bed-targeted companion; skips when bed unreachable at `ws://127.0.0.1:8765/` |
| `src/casino/tests/test_casino_config.py`          | Unit tests for `get_casino_config` / `get_surrender_multiplier` |
| `scripts/opencode.sql`                            | opencode user grants                  |
| `scripts/poker.sql`                               | Poker legacy migration                |
| `scripts/setup_privileges.sql`                    | Helper functions                      |
| `scripts/setup_test_db.py`                        | Test DB setup                         |
| `scripts/tictactoe.sql`                           | Tic-tac-toe anchor                    |
| `www/php/index.php`                               | Landing page                          |
| `www/skin/{scss,tmpl}/`                           | Landing-page skin                     |

## 13. Out of scope

- **Authentication wire-protocol** — bed's `AuthService`. Casino
  overrides it with its own `AuthService` because it must not depend
  on bed (last-write-wins registration on the same server). The
  shared credential primitives (`verifyMemberFound`, `has_password`,
  `checkpassword`) live in `bbsengine6.member`.

  **Note (2026-08-22, password column hardening follow-up):**
  Casino test fixtures MUST provision `engine.__member` rows via
  `casino.tests._ensure_test_member.ensure_test_member(args, moniker,
  plaintext, *, pool, ...)`, never via a raw
  `INSERT ... crypt('test', gen_salt('md5'))` SQL string and never
  via an unguarded `bbsengine6.member.setpassword` call. The
  `chk_member_password_bcrypt` CHECK constraint installed at every
  `bbsengine6.startup` rejects any non-NULL, non-bcrypt write —
  including the legacy `$1$` MD5-crypt hashes the previous fixture
  shape produced. The helper composes with
  `bbsengine6.member.audit_password_hash` (which exposes the
  column's structural flags as a `PasswordHashAudit` namedtuple —
  `is_bcrypt`, `length_ok`, `present`, `non_empty`, `is_md5crypt`):
  the helper INSERTs the row (loginid / email / credits reset on
  conflict — the fixture contract), then calls `setpassword` only
  when the audit reports the column is unhealthy
  (`is_bcrypt=False`, `length_ok=False`) or absent. On a fresh DB
  (`zoid6test`) the row is missing → `setpassword` runs. On a dev
  DB (`zoid6`) where the operator set their own bcrypt password on
  the fixture moniker the gate skips the write, preserving the
  operator's credentials across test runs. All seven fixtures
  listed in `0d84cf7` route their password writes through this
  helper; their monikers have additionally been renamed off the
  bare `'jam'` string to the `oc_test_*` family
  (`oc_test_blackjack`, `oc_test_blackjack_three`, `oc_test_features`,
  `oc_test_observer`, `oc_test_slots_1`, `oc_test_slots_2`,
  `slots_oc_test_1`, `blackjack_oc_test_1`) so the engine.__member
  row never collides with the operator's personal `'jam'` account at
  the member-row level. See `casino/TODO.md` "Test fixture
  migration: `gen_salt('md5')` → `gen_salt('bf')` (@since 20260822)"
  for the audit trail.
- **Daemon lifecycle** — bed.
- **Bank ledger storage** — casino wraps `bbsengine6.bank` for the
  `casino:house` treasury; the ledger itself lives in bbsengine6.
- **Per-member PostgreSQL role provisioning** — `bbsengine6.pgrole`.
- **The PHP framework** — the `www/` landing page is a Smarty
  template consumed by bbsengine6's PHP web layer, not a casino
  service. The actual casino UI runs in the BBS door or the
  WebSocket client.
- **Real-money gambling** — see the regulatory notice in `README.md`.
  This software is for development, testing, and demonstration only.
- **The `zoidweb2-casino.sql` snapshot** — orphaned Dec-2025
  schema; do not use.

## Coding Conventions

### PEP 8: Keyword Arguments

Following PEP 8, use `**kwargs` (not `**kw`) for keyword argument
unpacking in function signatures:

```python
# Good
def foo(arg1, **kwargs):
    value = kwargs.get("key", default)

# Bad  
def foo(arg1, **kw):
    value = kw.get("key", default)
```

Exception: BBS module entry points (`init`, `access`, `buildargs`,
`main`) may use `**kw` for consistency with the bbsengine module
loader interface.
