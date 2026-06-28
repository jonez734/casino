# Plan: Split `casino/src/casino/connect.py` + add `casino-client` CLI

> **Status:** Plan only — do not implement until approved.

## Goal

Separate the BED-server auth flow from the long-lived `CasinoClient` websocket
code, move the client into a real subpackage, and add a `casino-client`
console script so the standalone remote client can be run from the CLI.

## Resolved design decisions

1. **Split layout:** `auth.py` (BED auth + BBS entry points) + `client/`
   subpackage (`CasinoClient` + helpers + registry).
2. **Import compat:** update all call sites to the new modules; no shim.
3. **BBS entry points:** live in `auth.py` as a module; `main.py` is rewired
   to call `auth.connect(...)` directly for the auth menu entry.
4. **Auth prompt shape — D:** `async def auth_prompt(args, client) -> bool`.
   The prompt owns the `client.send(...)` call and returns `True` to
   continue, `False` to abort.
5. **Override form — function:** no Protocol/ABC. Override by reassigning
   `auth.auth_prompt` (module-level) or by setting `CasinoClient.auth_prompt`
   on a subclass (per-instance carve-out).
6. **Single source of truth:** `auth.auth_prompt` is the canonical handle.
   `CasinoClient.cmd_auth` resolves `self.auth_prompt or auth.auth_prompt`
   at call time so module-level swaps propagate.
7. **Async-capable prompt:** `auth_prompt` is `async` even though the default
   body is sync — sets us up for non-blocking credential sources later.
8. **CLI defaults:** `--host localhost` (matches `main.py:42`), `--port 8765`.
9. **CLI return code (POSIX):** `0` on a clean quit (client authenticated),
   `1` on early bail.
10. **Strict contracts:** tuple unpacking and bool returns are strict; no
    forgiving fallbacks.

## Target layout

```
casino/src/casino/
├── auth.py                # NEW — BED auth + BBS module entry points + auth_prompt
├── client/                # NEW subpackage
│   ├── __init__.py        # re-exports
│   ├── casino_client.py   # CasinoClient class (+ auth_prompt class attr)
│   ├── registry.py        # _clients, _current_moniker
│   ├── action_input.py    # ActionInputHandler, resolve_action
│   └── __main__.py        # NEW — `python -m casino.client`
├── client_cli.py          # NEW — `casino-client` console-script entry point
└── connect.py             # DELETED

casino/
├── bin/casino-client      # NEW — shell wrapper
└── pyproject.toml         # EDIT — add casino-client entry point
```

## File contents

### `casino/client/registry.py` (new)
- `get_client(moniker=None) -> CasinoClient | None` (current 22–26)
- `get_current_moniker() -> str | None` (29–31)
- `set_current_moniker(moniker) -> None` (34–37)
- Module state: `_clients`, `_current_moniker`

### `casino/client/casino_client.py` (new)
- `class CasinoClient` (current 139–742), with these changes:
  - Class attribute: `auth_prompt: Callable | None = None` — `None` means
    "fall through to `auth.auth_prompt`"
  - `cmd_auth` becomes async, resolves prompt at call time, sends through
    the connected client:

    ```python
    async def cmd_auth(self) -> None:
        from .. import auth
        prompt = self.auth_prompt or auth.auth_prompt
        await prompt(self.args, self)
    ```

  - `run()` calls `await self.cmd_auth()` instead of `self.cmd_auth()`
- `display_game_state` stays here, becomes `async` (it already is in the
  current code).

### `casino/client/action_input.py` (new)
- `resolve_action(input_str, actions) -> str | None` (65–97)
- `class ActionInputHandler(Completer)` (100–136)

### `casino/client/__init__.py` (new)

```python
from .registry import get_client, get_current_moniker, set_current_moniker
from .casino_client import CasinoClient
from .action_input import ActionInputHandler, resolve_action
```

### `casino/auth.py` (new)

```python
from __future__ import annotations

import argparse
import asyncio

from bbsengine6 import io, util, member

from .client import CasinoClient
from .client.registry import _clients, _current_moniker


# ---- Auth prompt: the single override point --------------------------

async def auth_prompt(args: argparse.Namespace, client: "CasinoClient") -> bool:
    """Default BED auth prompt.

    Prompts for moniker and (if the member has one) a password, then sends
    the auth message through `client`. Override this — or assign a new
    callable to `auth.auth_prompt`, or set `CasinoClient.auth_prompt` on a
    subclass — to customize the credential flow.

    Returns:
        True if the prompt completed (whether or not the server accepted),
        False to abort the connect flow.
    """
    moniker = io.inputstring("{var:promptcolor}Moniker: {var:inputcolor}", None, None)
    if not moniker:
        return False
    password = ""
    if member.has_password(args, moniker):
        password = util.inputpassword("Password: ")
    await client.send({"type": "auth", "moniker": moniker, "password": password})
    return True


# ---- BBS module entry points -----------------------------------------

def init(args, **kwargs) -> bool: return True
def access(args, op: str, **kwargs) -> bool: return True
def buildargs(args, **kwargs): return None


def _casino_table_fragment(**kwargs) -> str:
    from .client import get_client
    c = get_client()
    if c is None or c.current_table_moniker is None:
        return ""
    return f"{c.current_table_moniker} ({c.current_table_game_type}) players: {c.current_table_players}"


def init_remote_client_screen() -> None:
    from bbsengine6 import io as bbsio, screen as bbs_screen
    bbsio.screen.init()
    bbs_screen.register_bottombar_fragment(_casino_table_fragment)


def cleanup_remote_client_screen() -> None:
    from bbsengine6 import screen
    screen.unregister_bottombar_fragment(_casino_table_fragment)


def connect(args, **kwargs) -> "CasinoClient | None":
    """BBS entry point: connect to the BED server and run the auth prompt."""
    from .client import CasinoClient

    util.heading("connect to server")
    host = getattr(args, "host", "localhost")
    port = getattr(args, "port", 8765)
    io.echo(f"Connecting to {host}:{port}...")

    client = CasinoClient(args)
    client._loop = asyncio.new_event_loop()
    asyncio.set_event_loop(client._loop)

    if not client._loop.run_until_complete(client.connect()):
        client._loop.close()
        io.echo("Failed to connect", level="error")
        return None

    client._receive_task = client._loop.create_task(client.receive_loop())

    # Auth prompt is the single override hook — both paths route through it.
    if not client._loop.run_until_complete(auth_prompt(args, client)):
        client._loop.run_until_complete(client.disconnect())
        client._loop.close()
        io.echo("Auth aborted", level="error")
        return None

    client._loop.run_until_complete(asyncio.sleep(0.5))

    if not client.authenticated:
        client._loop.run_until_complete(client.disconnect())
        client._loop.close()
        io.echo("Authentication failed", level="error")
        return None

    _clients[client.moniker] = client
    _current_moniker = client.moniker
    io.echo(f"Connected as {client.moniker}, balance: {client.balance}")
    return client


def disconnect(args, client: "CasinoClient | None" = None, **kwargs) -> bool:
    from .client import get_client
    client = client or get_client()
    if client is None:
        io.echo("Not connected.", level="error")
        return False
    client._loop.run_until_complete(client.disconnect())
    client._loop.close()
    if client.moniker in _clients:
        del _clients[client.moniker]
    if _current_moniker == client.moniker:
        _current_moniker = None
    io.echo("Disconnected.")
    return True


def main(args, **kwargs) -> bool:
    return connect(args, **kwargs)
```

### Override examples (for the README/docstring)

```python
# Moniker-only auth — no password prompt
async def moniker_only(args, client) -> bool:
    moniker = io.inputstring("Moniker: ").strip()
    if not moniker:
        return False
    await client.send({"type": "auth", "moniker": moniker, "password": ""})
    return True

# Module-level swap (affects BBS connect + CasinoClient.cmd_auth)
from casino import auth
auth.auth_prompt = moniker_only

# Subclass swap (affects only the standalone client)
from casino.client import CasinoClient
class BotClient(CasinoClient):
    auth_prompt = staticmethod(moniker_only)
```

### Override resolution

| Site                              | Resolves to                                                  |
|-----------------------------------|--------------------------------------------------------------|
| `auth.connect()` (BBS)            | `auth.auth_prompt` (always)                                  |
| `CasinoClient.cmd_auth()` (REPL)  | `self.auth_prompt` if set on class/instance, else `auth.auth_prompt` |
| `casino-client` CLI               | `CasinoClient(...).cmd_auth()` → falls through to `auth.auth_prompt` |

`auth.auth_prompt` is the single source of truth; the class-attribute form
is the carve-out for "I want the standalone client to behave differently
than the BBS path."

### `casino/client_cli.py` (new)

```python
"""Console-script entry point for the standalone casino remote client.

Usage:
    casino-client [--host HOST] [--port PORT]
"""
from __future__ import annotations

import argparse

from .client import CasinoClient


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="casino-client",
        description="Standalone casino remote client (talks to the BED casino server).",
    )
    p.add_argument("--host", default="localhost", help="BED server host (default: localhost)")
    p.add_argument("--port", type=int, default=8765, help="BED server port (default: 8765)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = CasinoClient(args)
    client.run()
    return 0 if client.authenticated else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

### `casino/client/__main__.py` (new)

```python
from ..client_cli import main
raise SystemExit(main())
```

### `pyproject.toml` (edit)

```toml
[project.scripts]
casino        = "casino.__main__:main"
casino-client = "casino.client_cli:main"   # NEW
```

### `bin/casino-client` (new)

```sh
#!/bin/sh
python -W all -m "casino.client" "$@"
```

(chmod +x, mirrors `bin/casino:1-3`)

## Call-site updates

### `casino/src/casino/main.py`
- L10: `from . import connect` → `from . import auth`
- L70 menu tuple: `("C", "Connect", "connect")` → `("C", "Connect", "auth")`
- L82 menu tuple: `("X", "Disconnect", "connect.disconnect")` → `("X", "Disconnect", "auth.disconnect")`
- L99: `connect.init_remote_client_screen()` → `auth.init_remote_client_screen()`
- L165: `connect.disconnect(args, client=remote_client)` → `auth.disconnect(args, client=remote_client)`
- L166: `connect.cleanup_remote_client_screen()` → `auth.cleanup_remote_client_screen()`
- L189 dispatch: add branch for `module == "auth" and subcommand is None`
  that calls `auth.connect(args, **run_kwargs)` directly, feeds result into
  the same `remote_client` capture path.
- L191: `if module == "connect" and subcommand is None:` → `if module == "auth" and subcommand is None:`

### `casino/src/casino/commands/*/lib.py` (6 files)
Swap the lazy import:
- `from casino.connect import get_client as _get_client` → `from casino.client import get_client as _get_client`
- `commands/game/lib.py:96` additionally: `from casino.connect import ActionInputHandler` → `from casino.client import ActionInputHandler`

### Tests (3 files, 18 import lines)
- `tests/test_client.py:59,72,99`: `from casino.connect import CasinoClient` → `from casino.client import CasinoClient`
- `tests/test_client.py:84`: `from casino import connect` → `from casino import auth`
- `tests/test_client.py:354,390`: `"connect.disconnect"` → `"auth.disconnect"` in menu tuples
- `tests/test_commands.py:250`: `from casino.connect import CasinoClient` → `from casino.client import CasinoClient`
- `tests/test_commands.py:241`: `"connect.disconnect"` → `"auth.disconnect"`
- `tests/test_action_completion.py:16,116,133,141,149,165,173`: `from casino.connect import ActionInputHandler` / `resolve_action` → `from casino.client import ...`

### Docs (path/import updates only)
- `tictactoe/README.md:147`, `yahtzee/README.md:122`: `connect.py` → `client/casino_client.py`
- `TODO.md:799`: `from casino.connect import ActionInputHandler` → `from casino.client import ActionInputHandler`
- `TODO.md:15,737,783-786,1522,1532`: leave as historical changelog text

## New tests to add

1. **`tests/test_auth_prompt.py`** — override plumbing:
   - `auth.auth_prompt = my_async_prompt` is honored by `auth.connect()` (mock the rest)
   - Subclassing `CasinoClient` with `auth_prompt = staticmethod(my_async_prompt)` is honored by `cmd_auth`
   - Default `auth_prompt` runs when nothing is overridden
   - Returning `False` aborts the connect flow cleanly
   - Empty moniker / EOF maps to `False`
2. **`tests/test_client_cli.py`** — `casino-client` script:
   - `--help` exits 0
   - `CasinoClient.auth_prompt` override propagates through the CLI path
   - Returns 0 if `client.authenticated`, 1 otherwise (without actually connecting — mock the client)
3. **`tests/test_moniker_only_auth.py`** — the `moniker_only` example from
   the docstring, as a regression test showing the override pattern works
   end-to-end.

## Execution order

1. Read `casino/src/casino/lib.py:runmodule` to confirm the direct-call
   branch in `main.py` is the right shape.
2. Create `casino/client/{registry,casino_client,action_input}.py` and `__init__.py`.
3. Create `casino/auth.py` with `auth_prompt` (D-shape) and BBS entry points.
4. Create `casino/client_cli.py` and `casino/client/__main__.py`.
5. Add `casino-client = "casino.client_cli:main"` to `pyproject.toml`.
6. Create `bin/casino-client` (chmod +x).
7. Update `main.py` (menu tuples, screen helpers, dispatch branch, special case).
8. Update the 6 `commands/*/lib.py` files and 3 test files for new import paths.
9. Update doc references in `tictactoe/README.md`, `yahtzee/README.md`,
   and `TODO.md:799`.
10. Add `tests/test_auth_prompt.py`, `tests/test_client_cli.py`,
    `tests/test_moniker_only_auth.py`.
11. Delete `casino/src/casino/connect.py`.
12. `pip install -e .` then `casino-client --help` and
    `casino-client --host localhost` smoke test.
13. `make test-unit` (per `Makefile:5`).

## Risks / notes

- **`cmd_auth` becoming async is the only behavior change** in
  `CasinoClient`. Single call site (`run()` line 693), mechanical change.
- **D-shape couples the prompt to `CasinoClient`** — the prompt is
  meaningless without a connected client to send through. Acceptable
  because the prompt only ever runs in that context.
- **Bool contract is strict** — no "moniker-or-None" alternative. If a
  future caller needs the moniker out-of-band, we'd add an `AuthIntent`
  dataclass; not needed today.
- **Module-level override (`auth.auth_prompt = ...`) is global** — affects
  every concurrent connection. Subclass form is per-instance. Document
  this clearly in the `auth_prompt` docstring.
- **`auth_prompt` is both the implementation and the override handle** —
  no separate private alias. The single function is the implementation,
  the single name is the override handle.
- **`lib.runmodule` dispatch for `auth`:** Step 1 is the gating read. If
  the loader does something unexpected (e.g. requires a `lib.py` sibling),
  the direct-call branch in `main.py` may need to be more elaborate.
