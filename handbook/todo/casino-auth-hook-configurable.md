# Casino: sign-in hook configurable from JSON (option 2)

Status: open. Decision: casino keeps its own hook for now (option 1). This note records the later step.

## Why casino is not the bed contract

Bed's `authenticate` (`bed.tools.authenticate`) is a synchronous credential prompt: it takes
`(*, directory, title, header, fd, store_token, moniker)` and returns `(moniker, token)`. It is the
contract `bbsengine6.module._stub_authenticate` describes, and it is what `bed.json` names as
`auth.authenticate`.

Casino's hook is a TUI step, not the bed contract:

    async def authenticate(args: argparse.Namespace, client: CasinoClient) -> bool

It calls bed's `authenticate` internally, then binds the token to the open WebSocket (a `reconnect`
envelope), and sets the client's moniker and balance. Resolving bed's `auth.authenticate` into
`CasinoClient.cmd_auth` would call a keyword-only function with `(args, client)` and fail.

## Option 2: a second contract for casino, named in casino's config

- [ ] Define a stub for the casino hook in bbsengine6 next to `_stub_authenticate`:
      `async (args, client) -> bool`, using the same `check_signature` rule. Async functions need
      their own stub, since `inspect.iscoroutinefunction` must match too.
- [ ] Add a key to casino's config (for example `casino.auth_hook = "casino.auth:authenticate"`), read
      once at startup with `resolve_callable(spec, stub)`.
- [ ] `CasinoClient.cmd_auth` uses the resolved hook when no class or instance attribute overrides it,
      keeping the current order: `self.authenticate`, then the deprecated `self.auth_prompt`, then the
      configured hook.
- [ ] A bad value fails at casino's startup with the key and spec named, not at the first sign-in.
- [ ] Tests: good value resolves; a sync function is rejected; a wrong keyword is rejected; the
      deprecated `auth_prompt` alias still wins over the configured hook.
- [ ] Pty check of the casino TUI sign-in from the top line after the change.
- [ ] Spec: `casino/docs/AUTH.md` section B describes the configured hook and its contract.

## Not in scope

- Changing bed's `authenticate` contract. Bed's stays synchronous and keyword-only.
- Round-view. It calls bed's `authenticate` directly (through `viewer_login`), so it is covered by the
  bed contract and does not need this hook.
