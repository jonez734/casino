# Casino - Not Implemented Features

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
- [X] 13. SIGHUP reload - Reload config without full restart
- [X] 14. Auto-restart - Watchdog/retry on crash (--autorestart, --restart-delay, --max-restarts)
  - CLI: --autorestart/--no-autorestart, --restart-delay, --max-restarts
  - bed.json: bed.autorestart, bed.restart_delay, bed.max_restarts
