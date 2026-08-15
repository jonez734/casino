# casino — Specification

> **Last updated:** 2026-08-03.
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
9. [Cross-reference map](#9-cross-reference-map)
10. [Authoritative file index](#10-authoritative-file-index)
11. [Out of scope](#11-out-of-scope)

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
                │ bbsengine6 BBS │         │ casino-client  │
                └────────────────┘         └────────────────┘
```

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

## 6. Standalone TUI client

`casino-client` is a long-lived `CasinoClient` WebSocket client
(`src/casino/client/casino_client.py`) that authenticates with the
BED server and exposes table management, blackjack, poker,
tic-tac-toe, chat, and bank operations from the command line.
Useful for sysops and CI smoke tests.

Auth always prompts for password (commit `ec0138e`) and reports a
specific failure reason (`Member not found`, `Invalid moniker`,
`Authentication service unavailable`).

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
  by `startup.py` at bring-up. Includes `schema.sql`, `account`,
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

## 9. Cross-reference map

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

## 10. Authoritative file index

| Path                                              | Role                                  |
|---------------------------------------------------|---------------------------------------|
| `pyproject.toml`                                  | Manifest (4 console scripts + 4 poker variants) |
| `src/casino/__init__.py`                          | Package init (BBS module entry)      |
| `src/casino/__main__.py`                          | `python -m casino` entry              |
| `src/casino/main.py`                              | Door-mode menu                        |
| `src/casino/auth.py`                              | BED auth + BBS entry                  |
| `src/casino/lib.py`                               | Card / Hand / Shoe / CasinoPlayer + bottombar |
| `src/casino/config.py`                            | Env-var config loader                 |
| `src/casino/client_cli.py`                        | `casino-client` console-script entry  |
| `src/casino/startup.py`                           | Schema import                         |
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
| `scripts/opencode.sql`                            | opencode user grants                  |
| `scripts/poker.sql`                               | Poker legacy migration                |
| `scripts/setup_privileges.sql`                    | Helper functions                      |
| `scripts/setup_test_db.py`                        | Test DB setup                         |
| `scripts/tictactoe.sql`                           | Tic-tac-toe anchor                    |
| `www/php/index.php`                               | Landing page                          |
| `www/skin/{scss,tmpl}/`                           | Landing-page skin                     |

## 11. Out of scope

- **Authentication wire-protocol** — bed's `AuthService`. Casino
  overrides it with its own `AuthService` because it must not depend
  on bed (last-write-wins registration on the same server). The
  shared credential primitives (`verifyMemberFound`, `has_password`,
  `checkpassword`) live in `bbsengine6.member`.
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
