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

  **DONE**: Added `server.broadcast()` calls in `_handle_game_action` and `_handle_bet` in `api/handler.py`. After each player action (hit, stand, double, split, surrender, bet), game_state is now broadcast to all clients connected to the table's WebSocket path.

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

**Status:** Not started (depends on bbsengine6 message system being implemented first)

See `bbsengine6/TODO.md` for full specification.

Note: The message system is the base layer. The notify system builds on it (for real-time delivery), so bbsengine6 message system must be implemented first.

### Casino-Specific Integration

- **Channel naming:** `casino:table:{moniker}` for table game updates
- **Personal channel:** `member:{moniker}` for direct member-to-member messages

**Integration steps:**

1. Add channel subscription message handlers in `api/handler.py`:
   - `subscribe_channel` - subscribe session to a channel
   - `unsubscribe_channel` - unsubscribe from a channel

2. On `join_table`: auto-subscribe to `casino:table:{moniker}`

3. On `watch_table`: also subscribe to `casino:table:{moniker}` (unifies player/watcher logic)

4. Replace `server.broadcast(message, table_moniker)` with `server.publish(channel, message)` in:
   - `api/handler.py:handle_broadcast()` for game_state and chat messages
   - `_handle_game_action()` after each action
   - `_handle_bet()` after bets

5. On authentication (`auth` message): auto-subscribe to `member:{moniker}` for direct messages

6. Update `startup.py` to include new SQL files

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

## Phase 2: Expand Message System (Future)

After Phase 1, expand message system to include notify features (persistence, groups, rate limiting, blocking, etc.). See bbsengine6/TODO.md for details.

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
