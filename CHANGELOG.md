# Changelog

All notable changes to `casino` are recorded here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
