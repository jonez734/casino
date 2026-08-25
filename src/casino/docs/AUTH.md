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

## Member vs casino player

Casino sits on top of the BBS member layer (`bbsengine6.member`) and
adds a **casino player record** (`casino.__player`) per member. The
two rows have distinct responsibilities:

| Identity | Table | Holds |
|---|---|---|
| BBS **member** | `engine.__member` | BBS-level credentials (moniker, password), global `credits`, flags (SYSOP / APPROVED), email |
| **Casino player** | `casino.__player` | Casino-specific state: `lastplayed`, `attrs`, per-game `stats` counters |

The casino player row is keyed by `moniker citext NOT NULL PK`
(globally unique) with `membermoniker citext` as a nullable FK to
`engine.__member(moniker)` (`casino/src/casino/sql/player.sql`).
The legacy 1:1 shape is preserved on the lazy-materialize path
(`ensure_casino_player` INSERTs `moniker = membermoniker`), but the
schema permits **many casino rows per BBS member** — a single account
can hold distinct casino player identities, each with its own
`moniker`, `stats`, and `attrs`. The PK on `moniker` is global (not
per-member), so a given `moniker` value can only be claimed once
across the entire casino. "Many players" therefore means both many
BBS members playing concurrently **and** multiple casino rows per
member (the latter is a follow-up; existing callers see no
behavioural change because the lazy-materialize still seeds
`moniker = membermoniker`).

Members are created by a sysop via the `bbsengine6-console` flow
(`console.member.add`); casino never creates members. The casino
player row is **lazily** materialized the first time a member touches
casino, via
[`casino.services.player.ensure_casino_player`](../services/player.py),
called from both entry paths:

- WS-client auth: `PlayerService.authenticate` calls the helper on
  every successful login (with `audit=False` so the wire stays clean).
- Door-mode facade: `lib.CasinoPlayer.__init__` calls it on every
  construction (with `audit=True` so `casino --debug` shows who was
  auto-materialized).

When `audit=True` and a row is newly created, one
`io.echo(..., level="debug")` fires with the membermoniker. Subsequent
constructions for the same member are silent. There is no explicit
`casino init <moniker>` step in v1 — the audit echo is the sysop's
window into "who got auto-created." See `SPEC.md` §2.1 for the full
rationale.

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

Casino has two paths into the server, both ending at the same
captured `_bearer_token`:

### A. Bearer-token path (the no-prompt path)

When `args.token_file` points at a non-empty file (the operator ran
`bed auth login` ahead of time, or a previous `casino` invocation
wrote it), `casino.auth._connect_with_token` reads the token,
opens the WebSocket, and binds the token to the socket via
`auth reconnect`:

```json
C→S {"type":"reconnect","token":"…"}
S→C {"type":"reconnect_result","success":true,"moniker":"alice",
     "is_sysop":false,"session_id":"…","token":"…",
     "expires_at":"…","balance":42,"replayed":null}
```

The server rotates the token on every successful reconnect
(`bed.api.auth._handle_reconnect` mints a fresh record and
deletes the old one), so the `reconnect_result.token` field
captured below is the only valid token from this point on. The
rotated token is also written back to the token file by
`_connect_with_token` (mode 0600) so the next `casino` invocation
does not retry a now-revoked token.

### B. Prompt-driven path (the `bed auth`-delegated path)

When no token file is present, `casino.auth.auth_prompt` drives
the login:

1. The `moniker:` / `password:` prompts come from
   `bed.tools.auth._collect_credentials` -- the same helper
   `bed auth login` uses -- so the prompt UX is byte-identical
   to `bed auth login` (`{var:promptcolor}moniker: {var:inputcolor}`
   and `{var:promptcolor}password: {var:inputcolor}` with
   `{var:inputcolor}` ending each prompt).
2. The actual login round-trip happens on a one-shot
   `bed.client.BedConnection` via `BedAuthServiceClient.login`.
   The casino WebSocket is NOT used for this round-trip, so
   the `moniker` / `password` strings never appear on the
   operator's primary session socket.
3. The freshly-minted bearer token is persisted to the default
   token file via `bed.tools.auth._persist_token` (the same
   helper `bed auth login` uses), so the next `casino`
   invocation finds it and short-circuits via path A.
4. The token is then bound to the casino WebSocket via the
   same `auth reconnect` envelope path A uses:

```json
C→S {"type":"reconnect","token":"…"}
S→C {"type":"reconnect_result","success":true,"moniker":"alice",
     "is_sysop":false,"session_id":"…","token":"…",
     "expires_at":"…","balance":42,"replayed":null}
```

The server replies to `reconnect` with `reconnect_result` (not
`auth_result`); `CasinoClient.handle_message` handles both
envelopes identically. See "Bearer token capture" below.

The legacy `{"type":"auth","moniker":..,"password":..}` envelope
is no longer sent from casino. The server's
`bed.api.auth._handle_auth` accepts only moniker+password
credentials and would reject a token envelope there, so the
prompt path sends `reconnect` (which is the same envelope
`_connect_with_token` has always sent). The prompt UX is
unified; the wire shape is unified with the existing token-file
flow.

`CasinoClient.handle_message` extracts the `token` field on a
successful `reconnect_result` (or `auth_result`) and stashes it
on `self._bearer_token` (see
`casino/client/casino_client.py:113-130`). The existing
`CasinoClient.send` (`casino_client.py:68-86`) already auto-injects
that token on every wire call — the fix was just to make sure
`handle_message` populates it from the auth reply.

## Bearer token capture

The capture path is one block in `handle_message`:

```python
if msg_type in ("auth_result", "reconnect_result"):
    if msg.get("success"):
        # …mark authenticated…
        token = (msg.get("token") or "").strip()
        if token:
            self._bearer_token = token
```

Four invariants:

1. **Successful reply only.** A failed `auth_result` /
   `reconnect_result` does not touch `_bearer_token`. A client
   that already has a token from a prior login keeps it; a fresh
   client stays at `None`.
2. **Whitespace stripped.** A trailing newline from a token file
   (or a noisy log re-emit) does not leak onto the wire.
3. **Empty / missing token is a no-op.** The legacy standalone /
   door-mode AuthService envelope has no `token` field. `_bearer_token`
   stays at `None` and `send` falls back to session-only payloads so
   the legacy shape is preserved.
4. **`reconnect_result` rotation unconditionally captures.** The
   server rotates the token on every successful `reconnect`, so
   the freshly-returned token is the only valid one from this
   point on -- the previous token is gone from the token store.
   Capture is unconditional (not gated on the prior value being
   empty) so a rotation cannot leave the client riding a
   now-revoked token into the next op.

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
