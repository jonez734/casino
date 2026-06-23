# Casino - Not Implemented Features

## Blackjack Missing Features

- [X] 1. **Surrender** - Player can surrender mid-hand, forfeit 50% of bet
- [X] 2. **5-card Charlie** - Automatic win with 5 cards without busting
- [X] 3. **Dealer soft 17 rule** - Configurable table rule: dealer hits or stands on soft 17 (A+6)
- [X] 4. **Face-down dealer card** - Standard blackjack: show 1 card face-up, 1 face-down
- [ ] 5. **Statistics tracking** - Persistent win/loss/bust/blackjack stats per player
- [ ] 6. **Table access control** - Role-based access for who can play at which tables
- [ ] 7. **Card image resizing** - PIL-based PNG resizing for Tkinter card display

## Integration Test Issues

- [ ] Hole card: not hiding properly in integration tests (needs debug)

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
