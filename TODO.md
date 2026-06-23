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
- [ ] Fix WebSocket broadcast for spectators - spectators watching tables should receive game_state updates via `server.broadcast()` in `api/handler.py`

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
- WebSocket server (bed.py), table management, betting, banking, chat, and player/observer modes are working.

## Extended Statistics (Future)

The stats system uses a JSONB column for extensibility. Currently tracked:

**Generic (aggregate across all games):**
- wins, losses, pushes, net

**Game-specific (prefixed with game type):**
- blackjack.blackjacks, blackjack.busts, blackjack.surrenders, blackjack.hands_played

To add more game-specific stats, use the format `game_type.stat_name`:
- `poker.wins`, `slots.hands_played`, etc.

No database migration needed - just add the stat name to ALLOWED_STATS in dal/player.py
