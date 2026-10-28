# casino — Tournament play (initial plan)

> **Status:** plan only. Nothing in this document is implemented. Tournaments are a separate
> session from the persistence work in `POKER_PERSISTENCE.md`. Companion to `SPEC.md` §7 (poker)
> and `TODO.md`.

This document sets out what a poker tournament needs, what the codebase already provides, and
the decisions still open. It is a starting point for the tournament session, not a commitment
to a design.

## 1. What exists today

A cash table is the only poker format. The pieces a tournament can reuse:

| Piece                              | Where                                   | Reuse in a tournament                              |
|------------------------------------|-----------------------------------------|----------------------------------------------------|
| Table state, saved per action      | `services/poker.py`, `dal/poker_state.py` | Each tournament table is a normal persisted table. A restart resumes it. |
| Shoe, reshuffle, audit             | `shoe.py`, `dal/shoe.py`                | Unchanged: every table draws from its own shoe.    |
| Betting, streets, showdown         | `services/poker.py`, `poker/variant/`   | Unchanged.                                         |
| Turn clock and penalties           | `services/poker_clock.py`, `turn_seconds`, `clock_penalty` | Unchanged; the tournament sets the same per-table values. |
| Seating (`join_table`, seat order) | `services/poker.py`                      | Players are seated by the tournament, not by the player. |
| Lobby listing                      | `dal/table.py` (`type`), `list_tables`  | A tournament is listed by its own message (§6).    |

What does **not** exist:

- Tournament records (name, schedule, registration, status).
- A blind schedule. Each table has fixed `small_blind` and `big_blind`.
- Elimination. A player with no chips is not removed from the table.
- Table balancing and seat moves between tables.
- Prize distribution.
- Any rule for a player leaving a tournament mid-game.

## 2. Model

Four objects, with the poker table left as it is:

| Object              | Holds                                                                            |
|---------------------|----------------------------------------------------------------------------------|
| `Tournament`        | moniker, name, owner, status (`registering`, `running`, `finished`, `cancelled`), buy-in, starting stack, schedule, prize structure, created and started times. |
| `Registration`      | tournament, player, registered time, status (`registered`, `playing`, `busted`, `withdrawn`), finishing place. |
| `BlindLevel`        | tournament, level number, small blind, big blind, ante, minutes at this level.   |
| `TournamentTable`   | tournament, poker table moniker, the players seated at it.                       |

Storage is open. Two options:

- **A.** New tables under `casino.` (`__tournament`, `__tournament_player`, `__tournament_level`,
  `__tournament_table`), following `__poker_state` and `__shoe_event`. Recommended: it matches
  the audit and persistence design, and makes results queryable.
- **B.** Tournament state inside `casino.__table.attrs` for the tournament's row. Simpler, but
  mixes game state with settings and is hard to query for results.

## 3. Lifecycle

1. **Create.** An owner (or sysop) creates a tournament with a schedule and prize structure.
   Status `registering`.
2. **Register.** Players register and pay the buy-in. Chips are taken from the bank at
   registration (the existing bank path is the model). Registration closes at start or at a
   deadline.
3. **Start.** The tournament seats players at tables of `N` (default 9, configurable; a
   minimum of 2). Each table is an ordinary poker table with the current blind level. Status
   `running`.
4. **Play.** Tables run as cash tables would. Between hands, the tournament:
   - advances the blind level when the level's time has passed;
   - removes busted players (credits `0`) and records their finishing place;
   - rebalances tables when a table falls below a threshold, by moving a player between tables
     between hands;
   - merges the last tables into one when the field is small enough.
5. **Finish.** When one player holds all chips, the tournament finishes. Prizes are paid from
   the prize structure. Status `finished`.
6. **Cancel.** A tournament can be cancelled before start (buy-ins are refunded) or during play
   (sysop only; the policy for chips in play is an open question, §7).

## 4. Blind schedule

- A schedule is a list of levels, each with small blind, big blind, optional ante, and minutes.
- A level advances on the clock, not on hands played. A level change applies at the start of the
  next hand, never mid-hand.
- The schedule is stored on the tournament (`BlindLevel` rows), so a restart resumes at the
  correct level. The current level and its start time are part of tournament state.
- Each table's `small_blind` and `big_blind` are set from the tournament's current level when the
  level changes.

## 5. Elimination, balancing and placing

- **Busted:** a player whose credits reach `0` at the end of a hand is busted. Place is assigned
  as the number of players still in the tournament plus one at the moment of the bust. Ties among
  players busted on the same hand share the better place.
- **Rebalancing:** when tables differ in size by more than one seat, move the player on the
  biggest table with the fewest hands since their last move. Moves happen only between hands.
- **Final table:** when the remaining players fit one table, merge onto it.

## 6. Messages and access

Proposed `tournament_*` message types, handled by a `TournamentServiceHandler` in the same style as
`PokerServiceHandler`:

| Message                    | Who                    | Purpose                                      |
|----------------------------|------------------------|----------------------------------------------|
| `tournament_create`        | any member (owner)     | Create a tournament with schedule and prizes. |
| `tournament_list`          | any                    | List tournaments by status.                  |
| `tournament_register`      | any                    | Register and pay the buy-in.                 |
| `tournament_withdraw`      | registered player      | Withdraw before start (refunds the buy-in).  |
| `tournament_start`         | owner or sysop         | Close registration and seat players.         |
| `tournament_status`        | any                    | Level, time to next level, players left, own place. |
| `tournament_cancel`       | owner or sysop         | Cancel before start, or during play (sysop). |

The lobby does not change: poker tables keep their existing listing. A tournament's tables are
normal poker tables and appear in `list_tables` with `game_type: "poker"`. Tournament tables are
marked (for example, in `attrs`) so the lobby can show them as tournament tables.

Access follows the rules already used for poker: registration and status for any authenticated
member; start, cancel and table moves for the owner or sysop.

## 7. Open questions

1. **Storage (§2).** Dedicated `casino.__tournament*` tables (A), or `attrs` (B)?
2. **Chips in play at cancel.** Refund the buy-in only, or the remaining chips? Chips already
   won cannot be refunded without a settlement rule.
3. **Settlement.** Do buy-ins and prizes move money through the bank path, like blackjack bets?
   Poker cash tables do not yet settle to the database (see `TODO.md`, poker stats), so
   tournaments depend on that work.
4. **Level timing across restarts.** A level's clock is wall-clock time. After a restart, does a
   level that expired while bed was down advance immediately, or is the clock paused like the
   turn clock (`POKER_PERSISTENCE.md` §4)? Recommended: paused.
5. **Disconnected players.** A player who is not connected when their turn comes uses the table's
   clock penalty. Should a tournament use a stricter default than cash tables?
6. **Table size.** Default 9 and minimum 2 are proposals. Confirm.
7. **Prize structure.** Fixed percentages, a fixed table per field size, or owner-defined?
8. **Hand records.** Tournament hands should be recorded in `casino.__game` and `casino.__hand`.
   That work is still outstanding for cash poker too.

## 8. Build order

1. Settle §7 items 1, 2 and 3 with the owner.
2. Storage: migration for tournament tables, with the same grant pattern as
   `shoe_audit_migration.sql`.
3. `TournamentService` (state machine, blind levels, busting, placing) with unit tests and no
   sockets. Test with the same in-process pattern as `test_poker_persistence.py`.
4. Seating and rebalancing, tested with several tables in one process.
5. `TournamentServiceHandler` and the `tournament_*` messages, with access rules and a daemon test.
6. Client commands and rendering, following the poker client pattern.
7. Settlement, once the bank path for poker is in place.

## 9. Out of scope for the first version

- Sit-and-go and rebuy formats.
- Multi-table tournaments with re-entry.
- Bounties, satellites and seat tickets.
- Spectating a tournament table (watch mode).
