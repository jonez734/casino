# Changelog

All notable changes to `casino` are recorded here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### casino: capture bearer token from `auth_result` envelope

See `casino/docs/AUTH.md` for the full casino-side contract
(connection model, capture path, per-op re-injection, door-vs-BED
diagnostic). The BED-side kwargs-forwarding contract that makes
this work end-to-end lives in `bed/docs/BED_AUTH.md` "Adopting
AuthService in a custom router"; the sub-router half lives in
`zoid6/SPEC.md` §3.2.

`CasinoClient.handle_message` now stashes the `token` field from
the server's `auth_result` reply into `self._bearer_token`. The
existing `CasinoClient.send` already injects that token on every
wire call (defense-in-depth vs. the WS-bound session), but the
prompt-based legacy flow was throwing it away — the server minted
it, the client logged it as a print, and the very next op went out
without it. Result: `check_access` rejected the op as
`not_authenticated` even though `auth_result.success` was true.

Wired end-to-end with `bed.main.BED.start` forwarding
`session_registry` + `secret` + `token_store` + `instance_id` to
the router constructor (see `bed/docs/BED_AUTH.md` "Adopting
AuthService in a custom router" for the contract), and
`zoid6.api.handler.MessageRouter._register_module` forwarding
the same kwargs to sub-routers. The prompt-based flow now keeps
the token across the session; the door-mode legacy `AuthService`
envelope (no `token` field) is unchanged — `_bearer_token` stays
`None` and `send` falls back to session-only payloads.

### casino: slots color-tag consistency + box-render reset

Slots echo statements are migrated to the established color-tag
vocabulary used by blackjack and yahtzee, and the box render is
preceded by a `{/all}` reset so per-symbol colors don't inherit
stray attributes from prior echoes.

`casino/slots/__main__.py:_smoke_spin`:

- The bare `print("theoretical RTP:", ...)` line is converted to
  `io.echo(f"{{var:labelcolor}}theoretical RTP:{{var:valuecolor}} ...")`
  for consistency with the `target RTP` line above it. The previous
  `print()` form would have leaked `{var:labelcolor}` markup
  verbatim (AGENTS.md anti-pattern).
- An `io.echo("{/all}")` is inserted immediately before the box
  render so the grid starts from a clean attribute state.

`casino/slots/__main__.py:_run_demo`:

- All 11 summary-stat lines are converted from `print()` to
  `io.echo()` with `{{var:labelcolor}}/{{var:valuecolor}}`
  wrapping, matching the yahtzee stat-display pattern. The
  trailing `(theoretical)` annotation on the target RTP line is
  re-wrapped in `{{var:labelcolor}}` so the value stays visually
  distinct from its label.

`casino/slots/play.py`:

- `{title}` → `{var:titlecolor}` and `{normal}` → `{var:normalcolor}`
  on the "Spin result:" banner.
- `{error}` → `{level.error}` on the validation-error echo (in
  `_prompt_bet`) and on the no-win branch (in `run_one_spin`), as
  well as on the missing-arguments error (in `main`).
- `{success}` → `{level.ok}` on the win branch.
- An `io.echo("{/all}")` is inserted immediately before the box
  render in `run_one_spin`.

No new tests; the existing
`test_smoke_spin_emits_color_escapes` (test_slots_unit.py:699) and
the door-mode end-to-end tests (test_slots_integrated.py:421)
continue to pass without modification.

### casino: slots — end-of-render ACS reset + print→io.echo

`render_ascii()` ends with `{lrcorner}`, which leaves the terminal
in DEC graphics mode (ACS on). Any raw stdout write that follows
(e.g. `print()` in `_smoke_spin` / `_run_door`) is then rendered
as DEC glyphs — text below the slot grid was garbled.

`casino/slots/lib.py:render_ascii`:

- Append a trailing `{/all}` to the returned string. The token
  routes through `_handle_command`'s unconditional `_acs_off()`
  (`ESC ( B`) and then `_handle_slashall` (`ESC [ 0 m`), so the
  terminal is back in the default character set by the time
  `io.echo(render_ascii(result))` returns.

`casino/slots/__main__.py:_smoke_spin` and `_run_door`:

- Trailing `print(...)` calls that followed `io.echo(render_ascii(...))`
  are converted to `io.echo(...)` with `{{var:labelcolor}}/
  {{var:valuecolor}}` wrapping, matching the yahtzee stat-display
  pattern. Belt-and-suspenders: even with the trailing `{/all}`,
  routing all post-render text through `io.echo` keeps color and
  attribute state consistent.

`casino/AGENTS.md`: add a "Reset ACS at the end of render_ascii"
section parallel to the existing "Reset attributes before rendering
the slot grid" rule.

Tests: new `test_render_ascii_ends_with_acs_off` in
`test_slots_unit.py:TestRenderAscii` pins the contract — the last
ACS escape in the emitted stream must be `ESC ( B`. Existing
`test_io_echo_preserves_glyphs_and_box_drawing` and
`test_smoke_spin_emits_color_escapes` continue to pass.

### casino: yahtzee door-mode parity

Yahtzee now ships door-mode parity with blackjack and slots,
reversing the BED-only decision in `a307fde`. The `Y` menu
shortcut routes through `casino.commands.yahtzee.lib.play` to
`casino.yahtzee.game`, which sets up a `YahtzeeDealer` +
`YahtzeePlayer` (mirrors `casino.slots.player.SlotPlayer` /
`casino.slots.dealer.SlotDealer`) and runs the local play loop
in `casino.yahtzee.play`.

New files: `casino/src/casino/yahtzee/{player,game,play,__main__}.py`
plus `casino/src/casino/commands/yahtzee/{__init__,lib}.py`. The
`yahtzee/__init__.py:main` entry now uses `module.run` to
delegate to `yahtzee.game`, so callers like
`python -m casino.yahtzee` and `commands/yahtzee/lib.py:play`
get the standard init/buildargs/main machinery.

`commands/yahtzee/lib.py:play` branches on `args.direct`:
without it, dispatch lands in `yahtzee.game` (the BED-side
primary path); with `--direct`, dispatch lands in
`yahtzee.play` directly (the thin offline wrapper).

`yahtzee.game` and `yahtzee.play` both pass `module.check`
(via `bbsengine6.module._check_func_signature`), unlike the
existing `slots.play` and `blackjack.play` which are not
checked. This required removing `from __future__ import
annotations` from `yahtzee.play.py` so the `bool` / `bool |
None` return type is real (not a string) for the
annotation-introspecting `_check_func_return`.

29 new tests in `casino/tests/test_yahtzee_commands.py` cover
the commands subpkg, the door-mode dispatch, the help wiring
(two `util.heading()` calls per F1 — one for the action
prompt, one for the score-category prompt), and
`module.check` parity for all three yahtzee modules.

### casino: slots door-mode parity

Slots now ships door-mode parity with blackjack: the `S` menu
shortcut routes through `casino.commands.slots.lib.play` to
`casino.slots.game`, which sets up a `SlotDealer` + `SlotPlayer`
and runs the local play loop in `casino.slots.play`.

New files: `casino/src/casino/commands/slots/{__init__,lib}.py`.
The `slots/__init__.py:main` entry now uses `module.run` to
delegate to `slots.game`, matching the blackjack / yahtzee
pattern.

Both prompts in `casino.slots.play` (bet prompt, spin-again
prompt) are wired with `help=` callbacks so KEY_HELP / KEY_F1
redraws the option list. Each help callback calls
`bbsengine6.util.heading("play slots")` exactly once per F1
press.

24 new tests in `casino/tests/test_slots_commands.py` cover
the commands subpkg, the door-mode dispatch, the help wiring,
and `module.check` parity.

### casino: KEY_HELP wiring on every interactive prompt

Per the spec, every interactive prompt in the casino passes a
`help=` callback to `bbsengine6.io.inputchoice` so that
KEY_HELP / KEY_F1 redraws the prompt's option list. The
callback for each prompt calls `bbsengine6.util.heading()`
exactly once per F1 press — one F1 press = one heading. This
applies to:

- `casino.main.mainmenuhelp` — heading `"main menu"`
- `casino.commands.slots.lib.menu` — heading `"Slots"`
- `casino.commands.yahtzee.lib.menu` — heading `"Yahtzee"`
- `casino.slots.play._render_bet_help` — heading `"play slots"`
- `casino.slots.play._render_again_help` — heading `"play slots"`
- `casino.yahtzee.play._render_action_help` — heading `"play yahtzee"`
- `casino.yahtzee.play._render_score_help` — heading `"score category"`

The `main` menu used to call `util.heading("main menu")` once
before the inputchoice; the heading is now inside the
`mainmenuhelp` callback so F1 redraws the banner as well.

### casino: bottombar status surface with host:port, player, credits

The `casino` main menu now paints a status bar across the bottom
row of the terminal while the loop is running, mirroring the
`bed bank` tool. Three fragments are registered on
`bbsengine6.bottombar.registry_for("casino")` (leftmost first so a
notification fragment prepends even further left):

- a `<host>:<port>` fragment that flips to `direct` when the CLI is
  run with `--direct` (or when door mode bypasses the bed probe);
- a `<moniker>` fragment that reads the bound
  `_casino_registry.player.moniker`;
- a `<N credits>` / `<a credit>` / `<no credits>` fragment that
  reads the bound `_casino_registry.player.credits`.

`casino.lib.setbottombar()` now calls
`_ensure_screen_initialized()` before delegating to
`bbsengine6.bottombar.setbottombar`, mirroring the once-per-process
`io.screen.init()` guard in `bed.tools.bank._ensure_screen_initialized`
and `bbsengine6.ed.common.ui._screen_initialized`. This sets the
terminal scroll region (top/bottom margins) before any `setbottombar`
call lands, so the bottom row no longer scrolls off when output
overflows.

`casino.main.main()` registers the fragments on entry (via
`setbottombar`) and, in the outer `finally` block, calls
`lib._unregister_casino_fragments()` followed by
`lib._clear_bottombar()`. The cleanup echo uses the same
`{savecursor}{curpos:{height},0}{el}{reset}{restorecursor}` escape
sequence that `bed.tools.bank._clear_bottombar` and
`empyre/__main__.py` use, so the bottom row is erased and the
cursor is restored to where it was when `main()` was entered.

New tests in `casino/tests/test_bottombar.py` cover both fragments
in isolation (`TestCasinoBottombarFragments` — 9 tests: player,
credits pluralization, host:port/direct/defaults/empty), the
register/unregister lifecycle (`TestCasinoFragmentLifecycle` — 4
tests: idempotent register, full unregister, empty-tolerance), and
the once-per-process screen-init + cleanup-echo wiring
(`TestCasinoScreenInitGuard` — 5 tests: first-call init, repeat-call
skip, `setbottombar`-triggered init, no-reinit, escape sequence
shape). All 18 new tests pass.

### casino: migrate `bbsengine6.casino` imports to in-tree `casino.access`

The `bbsengine6.casino` stub module was removed in commit
`fdd8fe2`, but a number of in-tree call sites still imported from
it. The imports have been migrated to the in-tree `casino.access`
module, matching the access policy that ships with the package:

- `casino.api._auth` (line 55) — top-level import
- `casino.api.handler` (lines 352, 508) — lazy imports inside the
  per-op policy re-check
- `casino.commands.game.lib` (line 18), `casino.commands.table.lib`
  (line 19) — CLI tool entrypoints
- `casino.tests.test_auth_integration` (lines 395, 437) — assertion
  helpers
- `casino.tests.test_casino_access` (line 23) — the module under test
  (docstring updated to reference `casino.access`)

`casino.access` is the same policy that previously lived in the
dropped `bbsengine6.casino` stub, kept here in-tree so the
`casino` package stays self-contained and the per-op authorization
gate still runs against the same rule set.

### casino: fix `websocket.id` lookup key in session resolve

A pre-existing latent bug in
`casino.api._auth._get_session_state` and
`casino.api.handler.TableServiceHandler._legacy_session_id` was
uncovered when the blackjack flow tests first connected through
`WebSocketServer`. The legacy `websockets` library assigns
`websocket.id` to a `uuid.UUID` whose `int()` coercion yields a
128-bit value that is unrelated to the Python object id
`AuthService` used for session registration, so the 5-gate auth
pipeline was looking up a key that did not match the one written.

Both lookups have been corrected to try `id(websocket)` first
(matching the writer) and fall back to `str(websocket.id)` /
`int(websocket.id)` for the BED `SessionRegistry` path.

### casino: pass all 194 blackjack + access tests

`casino.sql.test_data.sql` now seeds a `__dealer__` pseudo-member
into `engine.__member` so the dealer's hand row in
`casino.__hand` can satisfy its FK to `engine.__member`, and the
casino player test row uses the actual `membermoniker` column
name. `test_blackjack_flow.py::test_betlog_view` now wraps its
view query in a transaction with `SET LOCAL ROLE jam` so the
`casino.betlog` view's `datepostedlocal` column (which joins
`engine.__member.loginid = current_user`) is populated by the
matching PG role rather than `NULL`.

Test client URIs in `test_blackjack_flow.py` were corrected to
point at the test server's actual port (`8766`) — the test server
was already on `8766` but the file's imports were rewritten for
the `casino.access` migration and the ten client URIs all matched
the test server. With these fixes, all 194 tests in
`test_blackjack_*.py` and `test_casino_access.py` pass.

### casino: merge `casino-client` into `casino`; bed is the default backend

The `casino-client` shell shim and console-script entry point are
gone. The merged `casino` CLI exposes the same bed-style flag set as
every other tool under `bed.tools`:

- `casino` (default) talks to the bed daemon at
  `ws://localhost:8765/`. The dispatcher probes the daemon first; if
  it's unreachable and `--direct` was not passed, exits non-zero with
  the bundled "rerun with --direct" hint (mirrors the bed tool
  convention).
- `casino --direct` runs the door mode: opens a Postgres connection
  pool via `bbsengine6.database`, starts a BBS session, and runs the
  interactive `casino.main` menu. Pass `--databasename` / etc. to
  override the connection.
- `casino --bed-host H --bed-port P` drives the bed daemon against a
  non-default endpoint. The full set is `--bed-host`, `--bed-port`,
  `--bed-path`, `--bed-call-timeout`, `--bed-probe-timeout`.

The bed-style arg names (`args.bed_host`, `args.bed_port`,
`args.bed_path`) replace the old `args.host` / `args.port` /
`args.path` everywhere — both at the CLI surface and on
`CasinoClient.__init__`. The door mode's BBS `connect` menu entry
(`auth.connect`) was updated to read the same names.

### casino: drop `casino-client` console-script entry point

`pyproject.toml` registers only `casino = "casino.__main__:main"`
now. `python -m casino.client_cli` still works for legacy callers
that imported the entry point directly.

### casino: extract `_routing` helper

New `casino/src/casino/_routing.py` mirrors `bed/tools/_routing.py`:
`build_client_args` registers the `--bed-*` + `--direct` flags, and
`select_backend` picks `"bed"` (default) vs `"direct"` based on
`probe_bed` reachability. Reuses
`bed.tools._routing.BedNotReachable` so the operator-facing hint is
shared with the rest of the bed tool family.

### casino: add `blackjack` subcommand to the merged CLI

`casino blackjack [...]` runs door-mode blackjack through the merged
entry point. The branch short-circuits before `_routing.select_backend`
because blackjack has no bed counterpart — it is door-mode only — so an
unreachable bed daemon never blocks the door-mode startup. A new
`blackjack = "casino.__main__:blackjack_main"` console-script entry
mirrors the existing `casino = "casino.__main__:main"` for symmetry.
The standalone `bin/blackjack` shim and `python -m casino.blackjack`
entry continue to work unchanged; the BBS launcher at
`letteredolive/build/lib/bbs.py:90` is unaffected.

### casino: clarify "decouple bank" CHANGELOG entry

The "decouple bank, member, channel, postoffice services from casino"
entry below claims "Casino's router just registers the already-imported
classes" for bank. That description did not match the actual state of
`casino.api.handler.MessageRouter.register_all`
(`casino/src/casino/api/handler.py:1270`): the casino router registers
table, game, bet, chat, slot, yahtzee, and tictactoe services only —
**not** bank. Bank message types are loaded by
`bed.defaultrouter.DefaultRouter.register_all`
(`bed/src/bed/defaultrouter.py:14`), which imports `BankServiceHandler`
from `bbsengine6.bank.api.handler`. The "already-imported classes"
claim applies to bed's router, not casino's. See `bed/SPEC.md:137`.

### lint: ruff cleanup across the tree

Drop unused imports, combine nested `with` statements, convert `%`
formatting to f-strings, and tidy import blocks so `ruff check` passes
clean (1113 errors at the start of the pass, 0 after).

### casino: install into the shared zoid6 venv

`deploy-tui` now runs `pip install .` into the active venv instead of
just building a wheel, so `deploytool casino.tui` installs casino into
the shared `/var/lib/zoid6/venv` alongside the other bbsengine6 services.

### casino: use `bottombar.registry_for('casino')` for the per-package registry

Each package now owns its own fragment registry, keyed by package
name. `bbsengine6.bottombar.registry_for('casino')` returns a
per-package registry so casino no longer competes with other BBS
modules for the global registry. `casino.lib` migrates its
register/unregister calls onto the per-package registry.

### MessageRouter: accept shared `channel_state` and `server` for pub/sub

The `MessageRouter` constructor now accepts shared `channel_state`
and `server` references so multiple routers in the same bed process
can cooperate on channel pub/sub without re-spawning the listener.

### fix: thread connection pool through PlayerService credential checks

`PlayerService.authenticate` now resolves a single
`bbsengine6.database` pool once per call and threads it through
`verifyMemberFound`, `has_password`, and `checkpassword` so the
entire credential check rides on a single borrowed connection.
Matches the CONN_POOL_PATTERN in `bbsengine6.member`.

### fix: client auth always prompts for password and reports specific failure reason

`casino-client` now always prompts for a password (was skipping when
the moniker was cached locally) and returns a specific failure
reason (`Member not found`, `Invalid moniker`, `Authentication
service unavailable`) so sysops can diagnose auth failures from
the CLI.

### Replace inline `SessionManager` with `CasinoSessionManager` subclass

`api/handler.py` now subclasses `bbsengine6.session.SessionManager`
as `CasinoSessionManager` so the casino-specific session state
(e.g. per-connection bottombar registry) is colocated with the
router.

### decouple bank, member, channel, postoffice services from casino

`bank`, `member`, `channel`, and `postoffice` services no longer
live in the casino package — they are imported from
`bbsengine6.{bank,member,channel}.api.handler` and
`postoffice.api.handler`. Casino's router just registers the
already-imported classes; the canonical implementations live in
their own repos.

### casino: simplify demo blurb, add game reference links

The casino demo blurb now links out to per-game reference pages
(`tictactoe/README.md`, `yahtzee/README.md`, `slots/README.md`)
instead of carrying the full rule set inline.

### casino: fix redundant 'wagers' in demo blurb

Cosmetic — the demo blurb had a duplicated "wagers" word. Removed.

### casino: update demo blurb to exclude cryptocurrency wagers and advise conservative jurisdictional compliance

Demo blurb updated to reflect the regulatory notice in `README.md`:
no cryptocurrency wagers; conservative jurisdictional compliance is
the operator's responsibility.

### casino: deploy-tui depends on build to produce whl

`make deploy-tui` now depends on `build` so the wheel exists before
the deploytool tries to ship it.

### casino: remove deploy target that built whl

The old `make deploy` (which built a wheel in-tree) is removed in
favor of the new deploytool-based targets.

### casino: add `deploy-www` and `deploy-tui` targets for deploytool

`make deploy-www` ships the `www/` Smarty landing page to the
production vhost. `make deploy-tui` ships the built wheel to the
target host.

### casino: add `www/` summary page with bbsengine6/Smarty templates

New `www/` directory with a Smarty landing page (`www/php/index.php`)
describing each game and linking to reference docs. Deployed via
`make deploy-www` to `/srv/www/vhosts/zoidtechnologies.com/html/casino/`.

### Makefile: add deploy target (aliases build)

`make deploy` is now a build alias.

### casino: remove commented-out engine message tables from `startup.py`

Cleaned up dead `engine.__message*` references from the schema
import.

### casino: simplify `startup.py`

- Removed bank schema setup (bank is `bbsengine6`'s responsibility).
- Reordered `hand` before `betlog` (FK dependency).
- Commented out engine message tables (gone in the notify → message
  migration).

### casino: bump `_version.py` to 0.0.1.dev202607071720 (build)

Release bump.

### casino: use `package=` kwarg for `bbsengine6.startup` at `__main__`

`bbsengine6.startup(package="casino")` registers the casino schema
under its package key.

### casino: align `lib.runmodule` kwarg with bbsengine6 (`prefix` → `package`)

`bbsengine6.lib.runmodule` renamed its `prefix=` kwarg to `package=`;
`casino.lib.runmodule` was updated to match.

### casino: TODO track prefix → package rename in `casino.lib.runmodule`

The rename above is tracked in `TODO.md`.

### casino: run `bbsengine6.startup` at `__main__` bring-up

`python -m casino` now invokes `bbsengine6.startup` automatically
so the database is up-to-date before the BBS module loads.

### casino: use `__pycache__/` + `*.pyc` + `build/` + `dist/` patterns for consistency

`.gitignore` updated to match the bbsengine6 / bed conventions.

### casino: ignore `src/casino/tk/` (stray bare-repo artifact)

`.gitignore` covers the empty `tk/` directory left over from a
bare-repo experiment.

### casino: migrate bottombar fragment registration to `bbsengine6.bottombar`

Fragment registration moves from casino-local code into
`bbsengine6.bottombar` so all packages share the same registry.

### casino: ignore `*.egg-info` build artifacts

`.gitignore` covers setuptools `*.egg-info/` directories.

### casino: remove superseded `--pidfile` entry, fix line-number cross-refs

`SPEC.md` had `--pidfile` listed as a CLI flag — bed owns it, not
casino. Removed; cross-references to `TODO.md` line numbers
corrected.

### casino: TODO entry for post-bring-up session plan

`TODO.md` gains a section documenting the post-bring-up session
plan (the rationale for `CasinoSessionManager`).

### casino: document per-hand money flow and rework plan in TODO

Per-hand money flow (bet → deal → outcome → settle) is documented
in `TODO.md` with a rework plan that landed in
`services/{game,bank}.py`.

### casino: read NULL credits as 0 in `get_player_balance` and `place_bet`

`NULL` credits (e.g. a freshly-created player with no balance row)
are now read as `0` instead of crashing the bet placement.

### casino: add empyre-style build/version targets to project Makefile

The `Makefile` now has `build` and `version` targets modeled on
the empyre / bed pattern (`make version` stamps `_version.py`,
`make build` produces a wheel).

---

For unimplemented features and future work, see
[`TODO.md`](TODO.md).
