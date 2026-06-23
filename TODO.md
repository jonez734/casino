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

## Notes

- All core blackjack features (hit, stand, split, double, insurance, push, blackjack 3:2 payout) ARE implemented and tested.

## Known Issues

- ~~**psycopg-pool 3.3.0 incompatibility**: The async database layer (`casino/dal/aiosql/`) is broken due to API changes in psycopg-pool 3.3.0. The `watch_table` feature fails with "object _AsyncGeneratorContextManager can't be used in 'await' expression". **Fix**: Downgrade to psycopg-pool 3.1.0 with `pip install psycopg-pool==3.1.0`~~ - RESOLVED (bbsengine6 now handles both 3.1.x and 3.3.0+ automatically)
- WebSocket server (bed.py), table management, betting, banking, chat, and player/observer modes are working.

## Pending Workstreams

### Workstream 2: Make test_player_observer.py Pass

**Status:** Pending

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

---

### Workstream 3: Update bbsengine6 Database Spec

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
