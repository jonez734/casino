# Specification: `casino/src/casino/bed.py`

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

Total: 6 services handling 25 message types.

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
