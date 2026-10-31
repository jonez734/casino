# Blackjack multi-player test flakes

## Symptom

These tests drive real WebSocket servers and fail intermittently:

- `test_blackjack_three_hands.py::test_auth_create_join_play_three_hands`
- `test_blackjack_two_players_three_games.py::test_two_players_three_hands_with_dealer`
- `test_blackjack_console_member.py::test_console_member_create_then_play_three_hands`
- `test_new_features_integration.py::TestHoleCardIntegration::test_hole_card_hidden_integration`

Each run fails a different subset. Run alone, a file passes most of the time.

## What has been measured

Samples are small, so these are observations, not rates.

- Clean HEAD worktree (casino `c5602b7`): `test_blackjack_three_hands.py` failed 1 run in 5.
- Working tree with the debug change (`3e8174b`): the same file failed 2 in 5, and 0 in 3 on
  other runs.
- The full suite has failed one to three blackjack multi-player tests per run on both HEAD and
  the working tree.

The debug change does not appear to be the cause, but the samples are too small to rule it out.

## Likely area

The tests share a real WebSocket server and a real event loop. The suspects are:

- ordering of the `owns_tables` push relative to the `table_created` and `joined_table` replies
  (the push is scheduled after the handler returns, see `_push_owns_tables`);
- a receive loop reading a message that belongs to a later step;
- port reuse between tests that start a server.

The tests now skip `owns_tables` messages in their receive helpers (`tests/_ws_replies.py` and
the per-file clients). That removed one ordering source, but the flakes remain.

## Next steps

1. Run one file 50 times on HEAD and on the working tree, and record the failure count.
2. Log the order of messages each failing test receives, to see which reply arrives late.
3. Check whether each test's server is closed before the next test binds its port.
