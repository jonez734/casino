# Casino Auth — Bearer Token Capture from `auth_result`

## What it is

The casino CLI clients (`casino`, `blackjack`, `yahtzee`, `slots`)
all share a single `CasinoClient` class that speaks the BED wire
protocol. On a successful login, the server's `auth_result` envelope
contains a short-lived signed bearer token minted by
`bed.api.auth.AuthService`. The client must **capture** that token and
**re-inject** it on every subsequent op so the server's per-op
wire-token gate (which is preferred over the WS-bound session token)
can re-verify it against its token store on every call.

If the client discards the token, the very next gameplay op returns
`code=not_authenticated` even though `auth_result.success` was true.
That is the canonical regression that prompted this doc.

The full BED-side contract (login / reconnect / refresh / revoke,
token shape, CLI flags, persistence modes, the custom-router kwargs
contract) lives in `bed/docs/BED_AUTH.md`. This file documents only
the casino-side half.

## Connection model

The client opens a single WebSocket to a BED daemon (default
`ws://localhost:8765/`) and sends a flat envelope per op:

```json
C→S {"type":"bet","amount":50,"table_moniker":"t1","token":"…"}
S→C {"type":"game_state","table_id":42,"…":"…"}
```

The `token` field is **always injected by the client** when
`_bearer_token` is set. The client never relies on the server-side
WS-bound session token alone because the server-side gate re-checks
the token on every op and is the only authorization layer the
`casino.api._auth.check_access` decorator sees.

## Login flow

```json
C→S {"type":"auth","moniker":"alice","password":"…"}
S→C {"type":"auth_result","success":true,"moniker":"alice",
     "is_sysop":false,"session_id":"…","token":"…",
     "expires_at":"…","balance":42}
```

`CasinoClient.handle_message` extracts the `token` field on a
successful `auth_result` and stashes it on `self._bearer_token`
(see `casino/client/casino_client.py:113-130`). The existing
`CasinoClient.send` (`casino_client.py:68-86`) already auto-injects
that token on every wire call — the fix was just to make sure
`handle_message` populates it from the auth reply.

## Bearer token capture

The capture path is one block in `handle_message`:

```python
if msg_type == "auth_result":
    if msg.get("success"):
        # …mark authenticated…
        token = (msg.get("token") or "").strip()
        if token:
            self._bearer_token = token
```

Three invariants:

1. **Successful auth only.** A failed `auth_result` does not touch
   `_bearer_token`. A client that already has a token from a prior
   login keeps it; a fresh client stays at `None`.
2. **Whitespace stripped.** A trailing newline from a token file
   (or a noisy log re-emit) does not leak onto the wire.
3. **Empty / missing token is a no-op.** The legacy standalone /
   door-mode AuthService envelope has no `token` field. `_bearer_token`
   stays at `None` and `send` falls back to session-only payloads so
   the legacy shape is preserved.

## Per-op re-injection

```python
async def send(self, message: dict) -> None:
    if not self.ws:
        return
    payload = dict(message)  # don't mutate the caller's dict
    token = (self._bearer_token or "").strip()
    if token:
        payload["token"] = token
    await self.ws.send(json.dumps(payload))
```

The injection is unconditional when `_bearer_token` is set. The
caller's dict is never mutated. Regression coverage lives in
`casino/tests/test_casino_client_token.py` (10 tests; both
injection and capture sides).

## CLI flags

```
--bed-host HOST            default: localhost
--bed-port PORT            default: 8765
--bed-path PATH            default: /
```

Token handling is transparent: there is no `--token` CLI flag. The
client either captures the token at login time or starts up with
no token at all. A future "resume from token file" option would land
in `connect()`, before any `auth` message is sent.

## Door-vs-BED diagnostic

The canonical probe for "is this daemon in BED mode" is to send
`create_table` (or `auth_refresh`) with a bogus token
(`"evil.injected"`):

- **BED mode** (AuthService registered, `token_persistence != none`):
  `check_access` rejects the op with `code=token_invalid`
  (signature failure on `_decode_token`).
- **Door mode** (no AuthService, no router registered, legacy
  `bbsengine6.net.defaultrouter.DefaultRouter` with
  `token_persistence=none`): the server's wire-token gate is
  not enforced, so the op goes through (or fails on its own
  policy grounds, depending on the message). The in-process
  equivalent — `auth_refresh` with a bogus token against
  `bed.main.BED.start()` — returns `code=token_invalid` and is
  pinned by `bed/tests/test_smoke_bed_mode.py`.

If the first op after a successful login returns
`code=not_authenticated`, the token capture is broken. Check
`CasinoClient._bearer_token` immediately after the `auth_result`
envelope is handled.

## See also

- `bed/docs/BED_AUTH.md` — full BED-side contract, including the
  "Adopting AuthService in a custom router" section that defines
  the kwargs forwarding contract (`session_registry`, `secret`,
  `token_store`, `instance_id`, `clock`) every router must
  accept.
- `zoid6/SPEC.md` §3.2 — `MessageRouter._register_module` forwards
  the same kwargs to sub-router constructors so `casino.api` handlers
  see the live `SessionRegistry` that `AuthService` bound.
- `zoid6/SPEC.md` §5 — diagnostic walkthrough for the live
  casino-vs-bed probe.
