# casino — Poker table persistence, card shoes, and the audit log

> **Status:** implemented on branch `main` (commits `199cf5c` through `4b00421`). Migration:
> `src/casino/sql/shoe_audit_migration.sql`. Companion to `SPEC.md` §7 (poker) and §8 (schema).

This document specifies how card shoes and poker table state are stored, how a bed restart
is handled, and what the `--audit` flag records.

## 1. Goals

1. **A restart never ends a game.** A poker table in progress resumes after `bed` restarts
   with the same seats, stacks, cards, bets, turn and shoe.
2. **Every card is accounted for.** The shoe holds the cards that have not been drawn. With
   `--audit`, every draw and burn is recorded with its card, draw count and shoe size.
3. **One shoe model for every card game.** Blackjack and poker both draw from a shoe, even when
   it holds one deck.

## 2. The shoe

A shoe is an ordered list of cards in the casino card format (`AH`, `10S`, `KD`), built from
one or more standard 52-card decks and shuffled together. It is defined in
`src/casino/shoe.py`.

| Setting          | Where set                          | Default | Meaning                                           |
|------------------|------------------------------------|---------|---------------------------------------------------|
| `shoe_decks`     | table `attrs` (jsonb)              | `1`     | Number of 52-card decks in the shoe.              |
| `shoe_threshold` | table `attrs` (jsonb)              | `0.8`   | Fraction of the shoe that may be drawn before it is reshuffled. |

### 2.1 Reshuffle rule

A shoe reshuffles on the draw that follows the point where `uses > size × threshold`, where:

- `size` is the full shoe size (`decks × 52`), fixed for the life of the shoe;
- `uses` is the number of cards drawn (and burned) since the last shuffle.

With one deck and the default threshold, `size × threshold` is `41.6`. The shoe reshuffles on
the 43rd draw: `uses` must first exceed 41.6, which takes 42 draws, and the next draw rebuilds the
shoe. The reshuffle is a fresh build of the full shoe, shuffled.

> **Change:** blackjack previously compared `uses` against the *remaining* card count, so its
> threshold moved as the shoe emptied. It now uses the shared rule above, so live blackjack
> shoes reshuffle at the configured fraction of a full shoe.

### 2.2 Burn cards

Poker burns one card before each street that deals board cards (flop, turn, river). A burn
counts toward `uses` and is recorded as a `burn` event under `--audit`. It is never dealt.

## 3. Storage

### 3.1 Blackjack

The shoe is stored on the table row, `casino.__table`:

- `shoe_cards` (`text[]`): the cards still in the shoe.
- `shoe_uses` (`integer`): the draw count since the last shuffle.

It is saved after every draw (`services/game.py`, `_draw_card`).

### 3.2 Poker

Each poker table has a `casino.__table` row with `type = 'poker'`, created when the table is
created (`PokerService.create_table`). The row is what `casino.__poker_state` references, so it
must exist before any state is saved.

The whole table is stored as one jsonb document in `casino.__poker_state`, keyed by table
moniker. The document contains:

- table settings: variant (by registry name), betting structure, blinds, buy-in limits,
  player limits, turn clock settings;
- the hand in progress: stage, current street, community cards, pot, current bet, last
  aggressor, whose turn it is;
- each player: seat, credits, hole cards, bets for the street and for the hand, flags;
- the shoe: cards, draw count, size settings, reshuffle count;
- `last_result`: the outcome of the most recent hand (see §5).

The document has a `format` version (currently `1`). A document with another version is
refused rather than guessed at.

## 4. Restart behaviour

- The poker state is saved **after every successful action** (`player_action`, `join_table`,
  `leave_table`, `start_hand`, `create_table`). A refused action changes nothing and saves
  nothing.
- On the first access to a table after a restart, the service loads it from
  `casino.__poker_state` (`PokerService._table`). The table stays open and play continues.
- On reload the **turn deadline is cleared**. The turn clock is paused, so a restart never
  costs a player their turn. The deadline is set again when the next turn starts.
- Blackjack needs no reload step: its shoe is read from the table row on demand.

### 4.1 What a restart does not preserve

- Open websocket sessions. Clients reconnect and authenticate again.
- Anything held only in the process: client-side prompts, unsent messages.

## 5. Hand results

When a hand ends, `last_result` is set on the table and returned on the next `poker_state` and
`poker_action_result` reply. Two kinds exist:

| `kind`         | When                                      | Fields                                              |
|----------------|-------------------------------------------|-----------------------------------------------------|
| `uncontested`  | Everyone but one player folds             | `winners`, `pot`, `shares`                          |
| `showdown`     | Two or more players reach showdown        | `winners`, `pot`, `shares`, `hand_name`, `hands` (each player's hole cards, best five and rank), `community_cards` |

`shares` maps each winner to the chips they receive; the shares always sum to `pot`. A split
gives each winner an equal share. Odd chips go to the first winner in seat order.

Winners are decided by the full evaluator tiebreak (`poker/variant/evaluator.py`: hand rank,
then pair values and kickers), not by hand category alone.

## 6. The audit log (`--audit`)

`casino --audit` turns on per-draw logging. Without the flag nothing is written to
`casino.__shoe_event`; table state is still saved (§4).

Each row in `casino.__shoe_event`:

| Column         | Type        | Meaning                                                                  |
|----------------|-------------|--------------------------------------------------------------------------|
| `id`           | `bigserial` | Row id; rows are ordered by it.                                          |
| `tablemoniker` | `citext`    | The table the event belongs to (references `casino.__table`).            |
| `handid`       | `bigint`    | Hand id, when known. Not yet set: poker hands are not yet recorded in `casino.__game`, so poker rows leave it `NULL`. |
| `kind`         | `text`      | `draw`, `burn` or `reshuffle`.                                           |
| `card`         | `text`      | The card drawn or burned. `NULL` for a reshuffle.                        |
| `draw_count`   | `integer`   | The shoe's draw count after the event.                                   |
| `shoe_size`    | `integer`   | The full shoe size at the time of the event.                             |
| `created`      | `timestamptz` | When the event was recorded.                                           |

A `reshuffle` row is written before the draw that triggered it. The table enforces that a
`reshuffle` has no card and a `draw` or `burn` has one.

Full shoe contents are not logged. A table's shoe can be reconstructed from its audit rows only
together with the saved shoe, and that is not a supported audit method; the audit log records
what happened, not the deck.

> **Future:** the audit level may be extended later (for example, logging every player action).

## 7. Database objects and grants

Created by `src/casino/sql/shoe_audit_migration.sql`. The migration is idempotent and must be run
by a role that owns, or can grant on, the `casino` schema.

| Object                        | Kind      | Grants                                                    |
|-------------------------------|-----------|-----------------------------------------------------------|
| `casino.__poker_state`        | table     | `bed`: select, insert, update, delete. `term`, `sysop`: all. `opencode`, `m_opencode`: select, insert, update, delete. `web`: none. |
| `casino.__shoe_event`         | table     | `bed`: select, insert (no update). `web`: select. `term`, `sysop`: all. `opencode`, `m_opencode`: select, insert, update, delete. |
| `casino.__shoe_event_id_seq`  | sequence  | `bed`: usage, select. `web`: select. `term`, `sysop`: all. `opencode`, `m_opencode`: usage, select. |
| `casino.__table`              | table     | `bed`: select, update (shoe columns for poker and blackjack). |

## 8. Operational notes

- Run the migration on each database before deploying code that uses it. Until it has run,
  poker actions fail with `relation "casino.__poker_state" does not exist`.
- Turn `--audit` on for a session that needs a record of every card. It adds one insert per
  card. Leave it off otherwise.
- Poker table rows are visible to sysop maintenance. Blackjack lobby listings filter on
  `type`, so poker rows are not listed as blackjack tables.

## 9. Test coverage

| Test module                               | Covers                                                        |
|-------------------------------------------|---------------------------------------------------------------|
| `tests/test_shoe.py`                      | Card format, size, reshuffle threshold, burns, restore, poker and blackjack drawing from the shoe |
| `tests/test_poker_persistence.py`         | Mid-hand restart, paused turn clock, poker row type, lobby exclusion, audit rows only with `--audit` |
| `tests/test_poker_play_flow.py`           | Reply rendering, play menu, raise accounting, showdown and fold results |
| `tests/test_poker.py`, `test_poker_integration.py`, `test_poker_clock.py` | Variants, betting, streets, showdown, clock |

Persistence tests run against `zoid6test`. They never run against `zoid6`.
