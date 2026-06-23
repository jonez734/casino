# Specification: `casino/src/casino/bed.py`

> **Note**: See [TODO.md](./TODO.md) for a list of unimplemented features and future work.

## Overview

**bed.py** implements the **BBS Engine Daemon (BED)** - a WebSocket server that provides real-time casino game services to BBS clients using the bbsengine6.net service registry.

## Purpose

- Accepts WebSocket connections from casino clients
- Routes messages to appropriate services (auth, table management, game play, betting, chat, banking)
- Maintains session state for authenticated users
- Broadcasts game state and chat messages to relevant players/spectators

## Key Components

### 1. `BED` Class

Main daemon controller managing server lifecycle.

**Attributes:**

- `args` - Command-line arguments (host, port, database credentials)
- `server` - WebSocketServer instance
- `router` - MessageRouter instance for dispatching messages
- `_running` - Boolean flag for daemon state

**Methods:**

- `async start()` - Initializes database pool, creates WebSocket server, registers services, starts listening
- `async stop()` - Gracefully stops the server
- `async restart()` - Stops and restarts the daemon

### 2. Command-Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `8765` | WebSocket port |
| `--debug` | false | Enable debug logging |
| `--foreground`, `-f` | false | Run in foreground (no daemonization) |
| `--pidfile` | - | Path to PID file |
| Database args | - | Via `databasebuildargs`: databasename, databasehost, databaseport, databaseuser, databasepassword |

### 3. Database Connection

- Uses bbsengine6 database pool
- Validates connection on startup with a connection test
- Graceful failure if PostgreSQL unavailable

### 4. Service Registration

The MessageRouter registers these services with the WebSocket server:

| Service | Message Types |
|---------|---------------|
| **AuthService** | `auth`, `ping` |
| **TableServiceHandler** | `list_tables`, `create_table`, `update_table`, `join_table`, `leave_table`, `watch_table`, `stop_watching` |
| **GameServiceHandler** | `hit`, `stand`, `double`, `split` |
| **BetServiceHandler** | `bet` |
| **ChatServiceHandler** | `chat_table`, `chat_global`, `emote` |
| **BankServiceHandler** | `bank_balance`, `bank_add`, `bank_remove`, `bank_transfer_request`, `bank_transfer_approve`, `bank_transfer_reject`, `bank_pending`, `bank_history`, `bank_list_all` |
| **PokerServiceHandler** | `poker_create_table`, `poker_join_table`, `poker_leave_table`, `poker_start_hand`, `poker_action`, `poker_fold`, `poker_check`, `poker_call`, `poker_bet`, `poker_raise`, `poker_all_in`, `poker_get_state`, `poker_list_tables` |

Total: 7 services handling 38+ message types.

### 5. Signal Handling

- Catches `SIGTERM` and `SIGINT` for graceful shutdown
- Handles Windows limitation (no signal handlers)

## Dependencies

- `bbsengine6.net.WebSocketServer` - WebSocket infrastructure
- `bbsengine6.util.getcurrentloginid` - BBS utilities
- `bbsengine6.database.buildargs` - Database argument parsing
- `casino.api.handler.MessageRouter` - Message routing and service coordination

## Startup Flow

1. Parse CLI arguments
2. Create BED instance
3. Set up signal handlers
4. Call `bed.start()`:
   - Build database args
   - Initialize database pool (with connection test)
   - Create MessageRouter
   - Register all services with WebSocketServer
   - Start WebSocket server on specified host:port
5. Keep running until cancelled or stopped

## Error Handling

- Database connection failure logs error and exits
- Unhandled exceptions in `main()` are caught, logged, and re-raised

## Gameplay

bed.py does NOT handle gameplay directly. It only sets up the WebSocket server and registers services. The actual gameplay is handled by:

- **GameServiceHandler** - handles `hit`, `stand`, `double`, `split` actions
- **BetServiceHandler** - handles `bet` messages

These services delegate to `casino/services/game.py` for game logic.

## Poker Implementation

### Overview

The poker implementation provides a complete poker game system with multiple variants, betting structures, and hand evaluation.

### Package Structure

```
casino/src/casino/poker/
├── __init__.py           # BBS module entry points
├── lib.py                # Core utilities (PokerDeck, PokerCard, HandRank, BettingStructure, BetLimits)
├── dealer.py             # PokerDealer class - manages deck operations
├── player.py             # PokerPlayer class - player state and actions
├── variant/              # Poker variant implementations
│   ├── __init__.py       # Variant registry
│   ├── base.py           # BaseVariant abstract class
│   ├── evaluator.py      # Hand evaluation (all rankings + tie-breakers)
│   ├── texas_hold_em.py  # Texas Hold'em
│   ├── omaha.py          # Omaha + Omaha Hi-Lo
│   └── seven_card_stud.py
├── services/
│   └── poker.py          # PokerService - game state machine, betting, showdown
```

### Supported Variants

| Variant | Hole Cards | Community Cards | Betting Structures |
|---------|-------------|-----------------|-------------------|
| Texas Hold'em | 2 | 5 (flop/turn/river) | No-Limit, Pot-Limit, Fixed-Limit |
| Omaha | 4 (must use 2) | 5 | Pot-Limit, Fixed-Limit |
| 7-Card Stud | 7 (no community) | 0 | Fixed-Limit |

### Betting Streets

- **Texas Hold'em / Omaha**: preflop → flop → turn → river
- **7-Card Stud**: third_street → fourth_street → fifth_street → sixth_street → seventh_street

### Hand Rankings

All poker hands are evaluated from Royal Flush (highest) to High Card (lowest):
- Royal Flush, Straight Flush, Four of a Kind, Full House, Flush, Straight, Three of a Kind, Two Pair, Pair, High Card

### Key Classes

**PokerDealer** (`poker/dealer.py`):
- `shuffle_deck(times)` - Shuffle the deck
- `deal_hole_cards(players, count)` - Deal hole cards to players
- `deal_community_cards(count)` - Deal community cards (burns first)
- `reset()` - Reset for new hand

**PokerPlayer** (`poker/player.py`):
- `receive_card(card_str)` - Add card to hand
- `post_bet(amount)` - Place a bet (handles all-in)
- `can_act()`, `can_check()`, `can_call()` - Action validation
- `collect_winnings(amount)` - Add winnings

**PokerService** (`poker/services/poker.py`):
- `create_table()` - Create a new poker table
- `join_table()` - Player joins table
- `start_hand()` - Start a new hand
- `player_action()` - Process bet/call/check/raise/fold/all-in
- `get_table_state()` - Get current game state

### Database Schema

Poker tables are defined in `scripts/poker.sql`:
- `casino.__poker_table` - Table configuration
- `casino.__poker_hand` - Hand history
- `casino.__poker_player_hand` - Player hands at showdown
- `casino.__poker_bet` - Betting history per street
- `casino.__poker_pot` - Pot/side pot tracking
- `casino.__poker_seat` - Player seats at tables
- `casino.__poker_stats` - Player statistics

### Commands

Poker commands are in `casino/commands/poker/`:
- `poker check` - Check (call if no bet)
- `poker call` - Call the current bet
- `poker bet` - Place a bet
- `poker raise` - Raise the bet
- `poker fold` - Fold your hand
- `poker allin` - Go all-in
- `poker show` - Show hand at showdown
- `poker muck` - Muck hand
- `poker hand` - Show your current hand
- `poker table` - Show table state
- `poker create` - Create a new table
- `poker join` - Join a table
- `poker leave` - Leave the table
- `poker list` - List available tables
- `poker start` - Start a new hand

## Coding Conventions

### PEP 8: Keyword Arguments

Following PEP 8, use `**kwargs` (not `**kw`) for keyword argument unpacking in function signatures:

```python
# Good
def foo(arg1, **kwargs):
    value = kwargs.get("key", default)

# Bad  
def foo(arg1, **kw):
    value = kw.get("key", default)
```

Exception: BBS module entry points (`init`, `access`, `buildargs`, `main`) may use `**kw` for consistency with the bbsengine module loader interface.

---

For unimplemented features and future work, see [TODO.md](./TODO.md).
