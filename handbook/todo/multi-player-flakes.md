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
`test_betlog_view`. Since then: three full runs and nine runs of the file alone were clean,
and five more full runs were clean in four of five. The fifth had two different failures,
`test_surrender_integration` and `test_player_observer`, which both depend on the WebSocket
server and the database. Record the betlog failure with its full output if it returns.

## Surrender flake: `test_new_features_integration.py::TestSurrenderIntegration::test_surrender_integration`

- Measured: 6 failures in 60 runs when run alone (about 10%).
- Evidence: the failing run's surrender reaches the handler with `session_id` set and an empty
  `table_moniker`, so the handler returns `not_at_table`. The test saw only `error`.
- The test's join reply is sent after the seat is set (`_set_seated` runs before the
  `joined_table` reply), so a plain join-then-act race does not explain it on paper.
- Open: why the action's session lookup has no table in some runs. Compare the key `_set_seated`
  writes with the key `_check_access` reads, under the test server's session manager, on a
  failing run.
- The test now waits for its reply with `receive_until` (`tests/_ws_replies.py`), so a failure
  names what arrived instead of a generic timeout.

## Player-observer flake: `test_player_observer.py::TestPlayerAndObserver::test_player_and_observer`

- Cause (confirmed with logs): the first bet dealt a dealer natural, so the bet's reply was
  already `phase: settled`. The test then hit a round that had settled, and the hit correctly
  returned "No active game". The same natural-round cause as the three-hand flake. The server
  was right; the test assumed an open round after the bet.
- Measured before the fix: 3 failures in 60 runs alone (about 5%).
- Fix (test only): the test checks a settled first deal, asserts the round settled on the bet,
  and returns early. A normal round still reaches the hit and the observer check.
- Measured after the fix: 0 failures in 60 runs alone.
- Checked with mutations in a scratch copy: breaking the hit makes the test fail on a normal
  round, so the hit path is still covered. Disabling the peek leaves the test passing, which is
  correct, since the round is then open.

## Blackjack flow flakes: `test_blackjack_flow.py`

Cause: `bet` can settle the round. A dealer natural, or a player natural, settles it inside
`place_bet`, so the bet reply is already `phase: settled` and the bet's betlog status is
`lost` or `won`, not `pending`. Tests that assumed an open round after the bet failed.

Fixed in the tests, not the server:

- `test_stand_after_bet`, `test_betlog_settlement`, `test_hit_then_stand`: a settled bet reply
  skips the stand or hit, and the bet is checked as settled.
- `test_betlog_view`: a settled round accepts `won`, `lost`, or `push` for the bet's status.
- `_verify_betlog`: accepts `pending`, or a natural settlement (`lost` or `won`), and rejects any
  other status.

Measured before: about 3 failures in 20 on the staged tree; 1 in 40 on the working tree.
Measured after: 0 failures in 80 runs of the file.

## Remaining risk

The natural test forces its shoe on the bet service's own `GameService`. If the bet and
game services are merged later, the test's shoe path must follow. Look for it under
`router.bet_service.game_service._shoes`.
