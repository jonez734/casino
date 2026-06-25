# Casino - Not Implemented Features

## BED bearer token

- [ ] See `bed/TODO.md` "Bearer token" — adopt `bed.api.auth.AuthService` for BED-mode authentication and reconnect. Replaces per-game `auth` implementations. Casino benefits strongly: lobby browsing, spectator mode, multi-table clients, bot accounts.

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
- Fixed `casino/services/game.py`: Added `player_hand` and `player_total` fields to `get_game_state()` return value for backward compatibility with tests and connect.py
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

**File:** `casino/src/casino/connect.py`

Remove hotkey concept - shortest-unique-prefix matching already works via prefix matching on action names.

**`resolve_action()` (lines 65-97):** Remove hotkey exact match, keep only prefix matching:
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
| `connect.py` | 372 | blackjack, poker, slots, yahtzee |
| `connect.py` | 497 | house, player |
| `connect.py` | 611 | balance, add, withdraw, transfer, pending, history, list, quit |
| `connect.py` | 651 | tables, create, update, join, leave, bet, hit, stand, msg, bank, quit |
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
from casino.connect import ActionInputHandler

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

## BED (BBS Engine Daemon) Improvements

**File:** `casino/src/casino/bed.py`

### Missing Features

- [ ] 1. Daemonization - `--foreground` flag exists but daemonization is never implemented
- [ ] 2. PID file management - `--pidfile` arg exists but is never used
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

