# Blackjack multi-player test flakes

## Cause (found)

A dealer natural (an ace or ten upcard with the matching hole card) settles the round inside
the bet. The peek in `_deal_dealer_and_peek` does this, and the round settles before the
player acts. About 1 round in 20 deals a natural, so roughly 14% of three-hand runs hit one.

The tests assumed every bet is followed by a stand, so the stand found "No active game" and
failed. The server was correct. The tests were wrong.

Fixed in the tests, not the server:

- `test_blackjack_three_hands.py` and `test_blackjack_console_member.py`: a bet reply already
  `phase: settled` is accepted as a complete round.
- `test_blackjack_two_players_three_games.py`: a natural on A's bet ends the round, B does not
  bet, and the expected betlog count is reduced by one for each such round.
- `test_new_features_integration.py::TestHoleCardIntegration`: a settled bet reply reveals the
  hole card, so the hidden-card check applies only to an open round.
- `test_blackjack_dealer_natural.py` (new): forces a natural with a fixed shoe and checks it
  settles on the bet and a stand then finds no game. Mutating the peek makes it fail.

## Results

- `test_blackjack_three_hands.py`: 4 failures in 30 before; 0 in 30, then 0 in 60 after.
- `test_blackjack_console_member.py`: 0 in 20 after.
- `test_blackjack_two_players_three_games.py`: 1 in 20 before the betlog fix, then 0 in 30.
- `test_new_features_integration.py::TestHoleCardIntegration`: 0 in 20 after.
- `test_blackjack_dealer_natural.py`: 0 in 10 after, and it fails when the peek is broken.

## Earlier notes

The first measurements (1 in 5 on HEAD, 2 in 5 with the debug change) were too few to show
anything. The debug change is not the cause: the failures were the natural round all along.

## Unexplained one-off

One run of the full suite failed `test_blackjack_flow.py::test_betlog_settlement` and
`test_betlog_view`. Three later full runs and nine runs of the file alone did not reproduce it.
Record it if it returns, with the run's full output.

## Remaining risk

The natural test forces its shoe on the bet service's own `GameService`. If the bet and
game services are merged later, the test's shoe path must follow. Look for it under
`router.bet_service.game_service._shoes`.
