# Changelog

All notable changes to `casino` are recorded here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### feat(casino/sql): casino.__player — promote moniker citext to PK

The casino player record (`casino.__player`) was previously keyed by
a legacy `id bigserial` PK with `membermoniker citext` as a
1:1-by-convention FK to `engine.__member(moniker)`. The new schema
drops the `id` column (and the `_id_seq` grants) and promotes
`moniker citext NOT NULL PRIMARY KEY` to the canonical key;
`membermoniker` stays as a nullable FK to `engine.__member(moniker)`.
The new shape permits many casino player rows per BBS member; the
legacy 1:1 contract is preserved on the lazy-materialize path
because `ensure_casino_player` INSERTs `moniker = membermoniker`,
so existing `WHERE moniker = <membermoniker>` queries still find
the single seeded row.

Changes:

- `sql/player.sql` — new schema; comment block documents the
  many-players-per-member rationale and points at the migration
  file. `__player_id_seq` grants removed (the sequence goes away
  with the column).
- `sql/player_migration.sql` (new) — idempotent migration: purges
  existing rows only when the legacy `id` column is still present,
  then drops `id CASCADE` (the cascade reaches `casino.player`,
  which is recreated by `sql/player_view.sql`), and adds
  `moniker citext` + `NOT NULL` + `pk_player_moniker PRIMARY KEY`.
  Re-runnable on already-migrated DBs without data loss.
- `sql/casino.sql` — `\i player_migration.sql` after `\i player.sql`
  so the schema and migration land together on a fresh DB.
- `sql/bootstrap_zoid6.sql` — replace the legacy stats-only migration
  block with the new player migration (existence-guarded on
  `id` present and `moniker` absent). Stats is included in the new
  schema, so no separate migration is needed for it.
- `sql/test_data.sql` — INSERT now writes both `membermoniker` and
  `moniker` (`jam` / `jam`) with `ON CONFLICT (moniker) DO NOTHING`
  so the seeded 1:1 shape survives re-runs.
- `startup/main.py` — citext comment now mentions both
  `casino.__player.moniker` and `casino.__player.membermoniker`.

Companion changes (separate commits):

- `refactor(casino)`: DAL + services query by `moniker` (the new
  PK); INSERT adds the column; return dict carries both
  `membermoniker` and `moniker`.
- `test(casino)`: integration tests pin `WHERE moniker` predicates
  and assert `row["moniker"] == <seed>` on freshly-materialized
  rows so the 1:1 lazy-materialize contract is documented.
- `docs(casino)`: `AUTH.md` "Member vs casino player" prose and
  the responsibility table now describe the many-players-per-member
  shape and note that the lazy-materialize preserves the legacy
  1:1 contract.

Verification:

- `psql zoid6 -f casino/src/casino/sql/player_migration.sql` —
  applies cleanly under table-owner perms (DELETE 1 → DROP COLUMN
  id CASCADE → ADD COLUMN moniker citext → SET NOT NULL → ADD
  CONSTRAINT pk_player_moniker). Re-runs are no-ops (row count 1 → 1).
- `\d casino.__player` — confirms new schema (membermoniker citext,
  moniker citext NOT NULL PK, no `id` column).
- `\d casino.player` (after recreating from `player_view.sql`) —
  view exposes both `membermoniker` and `moniker` columns plus
  `lastplayedlocal`.

### fix(casino): wire --token-file through merged CLI + CasinoClient.run

The bearer-token modules (`CasinoClient._bearer_token`,
`CasinoClient.send` auto-injection, `casino.auth._connect_with_token`)
all landed in earlier commits, but the merged `casino` CLI never
registered `--token-file` on its argparse, and
`CasinoClient.run()` never consulted `args.token_file`. So `casino
--token-file <path>` failed with `argparse: unrecognized arguments`
even when a valid token file was supplied, and `casino` (with no
flag) always fell through to the legacy prompt flow regardless of
`$XDG_RUNTIME_DIR/bed.token`.

This change wires the token-file flow end-to-end on the merged CLI:

- `casino.lib.buildargs()` now calls `casino.auth.buildargs(parser=parser)`
  so `--token-file` lands on the merged CLI's argparse. The flag mirrors
  `bed.tools._token.build_token_file_arg` so the default path and
  perm-check semantics are shared with `bed tools bank` /
  `bed tools auth login`.
- `casino.__main__.main()` resolves the default token-file path
  via `_token.ensure_token_file_arg(args)` after argparse parsing,
  then runs `_resolve_token_file(args)` which silently clears
  `args.token_file` to `None` when the resolved file is empty
  or missing — so `casino` falls through to the prompt cleanly
  before the operator has run `bed auth login`.
- `casino.auth._connect_with_token` now takes an optional
  `client=` kwarg: when supplied (by `CasinoClient.run`), the
  supplied client is mutated in place (loop, WS, reconnect reply
  state). The default `client=None` shape is preserved for the
  BBS-dispatch path (`casino.auth.connect`) and its existing tests.
- `CasinoClient.run()` now dispatches to
  `auth._connect_with_token(self.args, host, port, client=self)`
  when `args.token_file` is set; otherwise the legacy prompt
  flow (`self.connect()` → `self.cmd_auth()`) runs unchanged.

New regression pins in
`src/casino/tests/test_casino_cli_token.py`:
- `casino.lib.buildargs()` registers `--token-file`.
- `CasinoClient.run()` dispatches to `_connect_with_token` when
  `args.token_file` points at a non-empty file (and does NOT
  call `self.cmd_auth`).
- `CasinoClient.run()` falls through to the prompt when
  `args.token_file is None`.
- `_resolve_token_file` clears `args.token_file` when the
  default path resolves to an empty / missing file.
- `_connect_with_token(args, host, port, client=existing)`
  mutates `existing` in place (no second client constructed).

See `casino/docs/AUTH.md` for the full casino-side contract.
See `bed/TODO.md` "Bearer token" for the broader adoption
plan (lobby browsing, spectator mode, bot accounts).

### feat(casino): centralize casino player-record lifecycle (member → casino player)

Casino has its own auth on top of the BBS member layer
(`bbsengine6.member`) so many concurrent BBS members can play at once,
each with their own 1:1 casino player record. Until now the casino
player row (`casino.__player`) was only materialized via the WS-client
auth path (`PlayerService.authenticate → dal_player.get_or_create_player`),
so a member entering the door-mode casino menu had no casino row to
back their bottombar / stats / seat — the door-mode `CasinoPlayer`
facade rendered placeholders (`credits=1000`, `lastplayed=None`,
`stats={}`).

A single helper,
[`casino.services.player.ensure_casino_player`](src/casino/services/player.py),
now drives the lifecycle:

- `PlayerService.authenticate` (WS-client auth, every login) calls
  `ensure_casino_player(audit=False)` so the wire output stays clean.
- `lib.CasinoPlayer.__init__` (door-mode facade) calls
  `ensure_casino_player(audit=True)` so the bottombar, stats menu, and
  table-seat filter see real values from the first frame.
- When `audit=True` and a row is newly created, one `io.echo(..., level="debug")`
  fires with the membermoniker so a sysop running `casino --debug` can
  see who was auto-materialized. Subsequent constructions for the same
  member are silent.

Lifecycle is **lazy**: there is no explicit `casino init <moniker>`
step. Both entry paths converge on the same helper, so a row created
by one is visible to the other on the next read. The 1:1 member-to-player
shape is preserved (the FK in `casino/src/casino/sql/player.sql` is
unchanged); no schema migration needed.

Side cleanups:

- `lib.CasinoPlayer.__init__` populates `self.credits`, `self.lastplayed`,
  and `self.stats` from the freshly-materialized row (via
  `dal_player.get_player_balance` / `dal_player.get_player_stats`) so
  the placeholder values are no longer user-visible.
- Deleted unused `src/casino/dal/aiosql/player.py` — schema-drifted
  from the sync DAL and `sql/player.sql`, and not wired into any
  production path (`api/handler.py:23` is the only consumer of the
  async DAL and it only imports `async_dal_table`).

Regression coverage:

- `src/casino/tests/test_player_service.py::TestEnsureCasinoPlayer`
  (4 tests: idempotency, audit-on-create, audit-off, refactor smoke
  that `PlayerService.authenticate` calls the helper).
- `src/casino/tests/test_door_casino_player.py` (3 tests: row created,
  `credits` / `stats` populated, audit echo on first construction).
- `src/casino/tests/test_member_create_and_casino_auth.py::TestCreateMemberThenDoorModeCasinoPlayer`
  (1 test: the round-trip create-member → door-mode auto-creates
  the casino row, without a separate init step).

See `SPEC.md` §2 ("Member vs casino player") and
`docs/AUTH.md` ("Member vs casino player") for the rationale.

### fix(client/menu): bracket the inline prompt with `{f6}` seams around the option list

`casino_client.py:menu()`'s `io.inputchoice` prompt rendered the
status prefix (`[moniker] Balance: X`) on the **same line** as
the first option (`[T]ables`), and the last option (`[Q]uit`) on
the **same line** as the trailing `casino_client: ` prompt. The
status and the trailing prompt were glued to their neighbors with
no separator, so the operator saw a single horizontal line like:

```
[jam] Balance: 100000[T]ables  (list open tables)...[Q]uitcasino_client: 
```

instead of the expected layout (balance on its own line, each
option on its own line, prompt on its own line).

Two boundary `{f6}` seams are added:

- `status` now ends with `{f6}` so the balance lands on its own
  line above the option list.
- The trailing prompt is now prefixed with `{f6}` so
  `casino_client: ` lands on its own line below the last option.

Combined with the existing `{f6}` join between adjacent options,
the main menu's `{f6}` count is now `len(visible) + 1` (e.g. 8
visible options → 9 `{f6}` markers; 12 visible at a blackjack
seat → 13). The bank submenu's prompt string itself is unchanged
(8 options → 7 `{f6}` markers) — only the dispatcher's body now
emits label `io.echo()` calls (see next entry). Regression guards
updated in `tests/test_menu_inline_prompt.py`:

- `test_main_menu_prompt_has_one_f6_per_option_seam`: 7 → 9
- `test_main_menu_prompt_each_option_on_its_own_line`: chunk
  count is now `len(visible) + 2` (status, options, trailing
  prompt) instead of `len(visible)`.
- `test_main_menu_prompt_seated_at_blackjack`: 11 → 13.
- `test_main_menu_prompt_seam_count_matches_visible_plus_one`
  (renamed from `…_minus_one`): invariant is now
  `len(visible) + 1`.
- `test_main_menu_prompt_empty_visible_does_not_crash`: 0 → 2
  (still no per-option seams, but the two boundary seams are
  present).

### feat(client/casino_client): echo a label at every dispatch site in the main + bank submenus

Every option handler in the WS-client's main loop
(`CasinoClient.run`) and the bank submenu loop
(`cmd_bank_menu`) now emits a one-line `io.echo("Label")`
immediately before invoking the handler. Plain text, no markup —
the operator sees what action was just selected before the
handler's own output runs.

Main loop labels:

| Key | Label | Handler |
|---|---|---|
| `[T]` | `Tables` | `cmd_list_tables` |
| `[C]` | `Create` | `cmd_create_table` |
| `[U]` | `Update` | `cmd_update_table` |
| `[J]` | `Join` | `cmd_join_table` |
| `[L]` | `Leave` | `cmd_leave_table` |
| `[B]` | `Bet` | `cmd_bet` |
| `[H]` | `Hit` | inline `send({"type": "hit"})` |
| `[S]` | `Stand` | inline `send({"type": "stand"})` |
| `[M]` | `Message` | `cmd_table_chat` / `cmd_chat` |
| `[K]` | `Bank` | `cmd_bank_menu` |
| `[X]` | `TicTac` | `cmd_tictactoe_quick_play` |
| `[V]` | `Move` | `cmd_tictactoe_move` |
| `[N]` | `JoinT` | `cmd_tictactoe_join` |
| `[G]` | `Resign` | `cmd_tictactoe_resign` |
| `[Q]` | (none) | loop break |

Bank submenu labels:

| Key | Label | Handler |
|---|---|---|
| `[B]` | `Balance` | `cmd_bank_balance` |
| `[A]` | `Add` | `cmd_bank_add` |
| `[W]` | `Withdraw` | `cmd_bank_remove` |
| `[T]` | `Transfer` | `cmd_bank_transfer` |
| `[P]` | `Pending` | `cmd_bank_pending` |
| `[H]` | `History` | `cmd_bank_history` |
| `[L]` | `List all` | `cmd_bank_list_all` |
| `[Q]` | (none) | loop break |

Labels are emitted at the dispatch site (in `run` /
`cmd_bank_menu`), not inside the handler bodies — a future
caller that invokes a `cmd_*` method directly (e.g. from a
test) will not see a duplicate label.

### fix(client): main menu and bank submenu inline prompts — one option per line

Two `io.inputchoice()` prompts in the WS-client rendered the visible
option list as a single horizontal string — every `[X]label` fragment
was concatenated with no separator, so a 13-option menu printed as one
wall of `[T]ables,[C]reate,[U]pdate,...` text and was hard to scan.

Both prompts now put `{f6}` between adjacent option entries:

- `src/casino/client/menu.py:menu()` — main casino_client prompt.
  The `inline` join separator changes from `""` to `"{f6}"`, so the
  status prefix (`[moniker] Balance: X [Table: Y]`) is followed by
  one option per line and the trailing `casino_client: ` prompt
  sits on its own line.
- `src/casino/client/casino_client.py:cmd_bank_menu()` — bank
  submenu. The seven `[B]alance/[A]dd/[W]ithdraw/[T]ransfer/
  [P]ending/[H]istory/[L]ist all/[Q]uit` entries are now
  `{/all}`-closed with a `{f6}` before the next `{var:optioncolor}`
  opens, putting each on its own line.

The door-mode `mainmenuhelp` (`main.py:88-103`) and the WS-client
`_render_help` F1 callback (`client/menu.py:55-69`) already use one
`io.echo()` per option and are unaffected — `io.echo` appends `\n`
via `end=ECHO_END`, so each option naturally lands on its own line.
The inline-prompt case is the one that needed an explicit `{f6}`
because the option list is concatenated before being handed to
`io.inputchoice`. Documented in `SPEC.md` §6.1 ("Menu rendering
contract (WS-client inline prompts)"). Regression guard:
`tests/test_menu_inline_prompt.py` (new) — asserts the constructed
prompt string contains exactly `len(visible) - 1` `{f6}` separators
for both call sites.

### build: add `PREPARE_BUILD` macro to root Makefile

`casino/Makefile` lacked the `PREPARE_BUILD` helper that
`bed/Makefile:189-194` and `getdate_next/Makefile:32-36` already
have. Without it, the freshly-created `build/` inherits the
parent directory's setgid bit (mode `2775`), and setuptools'
`shutil.copystat` mirrors that mode onto the new dist-info
directory during `bdist_wheel` — which then EPERMs the
subsequent chmod in SELinux-enforcing + NoNewPrivs containers
(we lack `CAP_FSETID`).

The macro is identical to `bed/Makefile:189-194`, parameterized
over `$(1)` so the same definition can be reused if
`casino/src/casino/Makefile` ever needs the same treatment. The
comment block above it explains the full cause chain
(`copystat` → `setgid` → `EPERM` → "wheel build aborts") so
future readers don't have to re-derive it.

Called from both the `build` and `sdist` targets with
`$(CURDIR)` — same argument shape as `bed`'s `build` target.

Tracked in `zoid6/TODO.md` "PREPARE_BUILD standardization
(cross-project)" — that checkbox is now ticked.

### test(casino): create-member + casino-auth prompt integration tests

New file `casino/src/casino/tests/test_member_create_and_casino_auth.py`
exercises the create-member → casino-auth round-trip in 5 tests,
all marked `pytest.mark.integration`:

- `test_a1_create_via_member_setpassword` — insert a fresh
  `engine.__member` row, set the password through
  `bbsengine6.member.setpassword` (the public API the
  `console.member.add` flow uses), then round-trip the plaintext
  through `bbsengine6.member.checkpassword` to prove
  `crypt(plain, gen_salt('bf'))` matches.
- `test_a2_create_via_raw_crypt_sql` — same shape but inserts
  with `password = crypt('pw', gen_salt('bf'))` inline (the path
  `test_blackjack_flow.py` uses directly), again asserting
  `checkpassword` returns True.
- `test_prompt_sends_moniker_and_password` — pins the wire shape
  `casino.auth.auth_prompt` emits: with `io.inputstring` and
  `util.inputpassword` mocked, `client.send.await_args` is
  exactly `{"type": "auth", "moniker": ..., "password": "pw"}`.
- `test_b1_login_through_casino_prompt_setpassword_path` — drives
  `casino.auth.auth_prompt` against an in-process bed server
  using the real `PasswordCredentialProvider` (which calls
  `bbsengine6.member.checkpassword` for real); the member
  created in `(a.1)` is accepted, server replies
  `auth_result.success=True` with a minted token.
- `test_b2_login_through_casino_prompt_raw_crypt_sql_path` —
  same e2e flow but recreates the member via the `(a.2)` raw
  `crypt()` SQL path so the e2e covers both create paths
  symmetrically.

Each test uses a unique `alice_<label>_<secrets.token_hex(3)>`
moniker so reruns against a dirty DB self-heal. The four
DB-backed tests `skipTest(...)` when `engine.__member` is not
reachable; the mocked (b.1) prompt test runs regardless.

A self-contained `_BedServerHarness` keeps an in-process bed
`WebSocketServer` in a daemon thread with its own asyncio loop
(mirrors the pattern at
`bed/src/bed/tests/_auth_helpers.py:BedServerContext`); shutdown
cancels every task on the loop instead of awaiting
`WebSocketServer.stop()` so the close-handshake never hangs.

### build: depend on `clean` to wipe stale egg-info before each `python -m build`

The root `Makefile` `build` target (`casino/Makefile:63-64`)
now declares `clean` as a prerequisite so `casino/build/`,
`casino/dist/`, `casino/*.egg-info/`,
`casino/src/*.egg-info/`, and `casino/src/casino/*.egg-info/`
are wiped before every `python -m build` invocation. This
sidesteps the setuptools SOURCES.txt absolute-path failure
mode that surfaces when `src/casino.egg-info/SOURCES.txt`
carries forward absolute paths from a prior run (the working
tree currently has a stale `src/casino.egg-info/` from a
recent build).

`casino/Makefile:clean` was extended from `-rm *~` +
`make -C src clean` to also wipe `build/`, `dist/`,
`*.egg-info`, and the standard pytest / ruff / mypy cache
directories, mirroring the pattern shipped in
`zoid6/src/Makefile:118-124`. The `buildclean` target in
`src/casino/Makefile:32-33` (which already wipes
`build/ dist/ *.egg-info` for that subdir) is unchanged and
remains available for direct invocation.

### deploy-tui: install from `/srv/repo/casino/` wheel by default; `DEPLOY_EDITABLE=1` for editable

Part of the cross-monorepo Phase 1 work in `deploytool`'s
`--editable` flag (see `deploytool/CHANGELOG.md` `[Unreleased]`).
casino's `deploy-tui` target now matches the pattern shared by
`bbsengine6`, `bed`, `zoid6`, and `deploytool`.

Before: `casino/Makefile deploy-tui: install` called
top-level `install`, which was `$(PYTHON) -m pip install .` —
fresh build-and-install from the source tree on every
invocation. Not actually editable (changes don't show up
without re-running `pip install`), and also not going through
`/srv/repo/casino/`.

After:

- Default: `deploy-tui: build` then `pip install $WHEEL`,
  where `$WHEEL` is the most-recently-built wheel under
  `/srv/repo/casino/casino-*.whl` picked via `ls -t | head -1`.
- `DEPLOY_EDITABLE=1` (set by `deploytool --editable`):
  `$(MAKE) version` then `pip install --no-cache-dir -e .`
  from the project root, with `rm -rf src/casino.egg-info` to
  wipe stale absolute paths in `SOURCES.txt`.

Verified: `make -n -C casino deploy-tui` shows
`pip install /srv/repo/casino/casino-*.whl`; the same with
`DEPLOY_EDITABLE=1` shows `pip install -e .`.

### docs(casino): SPEC + README reflect startup subpackage structure

`casino/SPEC.md` gains a §8.1 "Startup module" subsection
documenting the bootstrap subpackage's 5-step flow (citext
install, schema ownership, schema import, schema privs,
class import) and the §12 file index replaces the single
`startup.py` row with three rows for the subpackage
(`startup/`, `startup/main.py`, `startup/checkcasino.py`).
`casino/README.md` "What's in this repo" tree replaces the
`startup.py` line with a `startup/` subpackage showing
`__init__.py`, `main.py`, `checkcasino.py`.

These changes reflect the bootstrap subpackage introduced by
the prior `feat(casino): introduce checkcasino module in
casino.startup` (`6b982a2`) and `feat(casino): wire
checkcasino into casino.startup.main` (`dd962e0`) commits.
No code changes.

### casino: wire `checkcasino` into `casino.startup.main`

Regression fix for the `permission denied for schema casino`
error surfaced on a freshly bootstrapped database after the
bbsengine6 `zoid6` ownership model landed (see
`bbsengine6/CHANGELOG.md` `[Unreleased] / backend: dedicated
zoid6 role owns the SECURITY DEFINER helpers` and
`bbsengine6/TODO_zoid6_role.md`).

`casino.startup.main` now calls `checkcasino.main(args,
conn=conn)` between the citext install (step 1) and the
`importsql("schema.sql")` (step 2). After `checkcasino` runs,
the `casino` schema exists and is owned by `zoid6`, so the
schema-priv re-assertion in step 3 (the
`database.manage_schema_priv("grant", "usage", "casino", role)`
loop) succeeds because `zoid6` can now `GRANT` on its own
schema.

The wiring is a single `checkcasino.main(args, conn=conn)`
call at the top of `main.py` plus the `from . import checkcasino`
import. No changes to the schema-priv re-assertion logic, no
changes to `casino/sql/schema.sql`, no changes to
`bootstrap_opencode.sql` — see `TODO.md` "`bootstrap_opencode.sql`
resets `casino` schema ownership back to `opencode`" for the
follow-up that pins the ownership model across the
out-of-band opencode bootstrap path.

### casino: introduce `checkcasino` module in `casino.startup`

- New module `casino.startup.checkcasino` mirrors the
  `engine`-schema block in `bbsengine6.backend.checkengine`
  (`checkengine.py:77-133`), but scoped to the casino project's
  own schema. It exists because the SECURITY DEFINER helper
  `public.manage_schema_priv` — which `casino.startup.main` calls
  to grant schema usage on the `casino` schema to `web`, `term`,
  `sysop`, `opencode` — is owned by `zoid6` (a `NOSUPERUSER`
  dedicated owner role created by
  `bbsengine6.backend.checkzoid6role`). A NOSUPERUSER role can only
  `GRANT` on objects it owns, so the `casino` schema must also be
  owned by `zoid6` for those grants to succeed.
- The module also runs the owner-gate from `checkengine.py:45-75`
  against the five SECURITY DEFINER helpers, so it refuses to
  continue if any of them is owned by a role outside the
  hard-coded allow-list `("zoid6", "postgres")`.
- Idempotent: creates the `casino` schema with
  `AUTHORIZATION zoid6` on fresh installs, or issues
  `ALTER SCHEMA casino OWNER TO zoid6` on BC upgrades where the
  schema is owned by another role. On a database where the schema
  is already owned by `zoid6`, `checkcasino.main(args, conn=conn)`
  is a no-op.
- 17 new tests in
  `src/casino/tests/test_startup_checkcasino.py` cover the
  contract (`init` / `buildargs` / `access`), the owner gate
  (mismatch → abort, not-installed → skip, pass → continue), the
  schema-create branch, the schema-reassign branch (opencode,
  postgres), the no-op branch (zoid6, dict and tuple row shapes),
  and a regression guard pinning the `HELPERS` allow-list in
  lock-step with `bbsengine6.backend.checkengine`.

The module exists but is **not yet wired** into
`casino.startup.main`; the wiring lands in a follow-up commit
(see next entry).

### casino: friendly "connection refused" message across `casino`, `blackjack`, `yahtzee`

All bin scripts that talk to the bed WebSocket daemon now render a
one-line friendly error via `bbsengine6.io.echo(level="error")` and
exit non-zero without a Python traceback when the daemon is not
listening. The error pattern is shared with `bedping`,
`bbsengine6-ping`, and `zoid6-ping` — the rendering lives in
`bbsengine6.net.ping` so future `websockets`-version fixes land in one
place.

Changes in `casino`:

* `CasinoClient.connect()` routes the `websockets.connect()` call
  through `bbsengine6.net.ping.connect(host, port, path=path,
  prog="casino")` so connection-level failures
  (`ConnectionRefusedError`, `OSError`, `asyncio.TimeoutError`,
  `WebSocketException`) raise `bbsengine6.net.ping.PingUnavailable`,
  which `CasinoClient.connect` catches and renders via
  `bbsengine6.io.echo(level="error")`. The local `import websockets`
  is kept (the library is still used elsewhere in the file) but the
  connect call itself no longer surfaces raw exceptions to the
  caller.
* `casino.blackjack.__main__` and `casino.yahtzee.__main__` now wrap
  the `module.run(...)` dispatch in a `try/except PingUnavailable`
  and exit non-zero with a friendly one-line message. Both files
  already caught `KeyboardInterrupt` and `EOFError`; the new branch
  slots in alongside those.
* New bin script `bin/casino-ping` is a 6-line shim around
  `bbsengine6.net.ping.main(prog="casino-ping")` and ships via
  `[tool.setuptools] script-files` in `casino/pyproject.toml`.

`casino/slots/__main__.py` is intentionally untouched: it does not
talk to a WebSocket daemon (`_smoke_spin`, `_run_demo`, `_run_door`
all use `print()` / `input()` locally), so it cannot raise
`PingUnavailable`.

The shared helper lives in `bbsengine6/py`; see the bbsengine6
changelog for the helper itself.

### casino: short-circuit `create_table` on duplicate moniker; surface per-table stats

When a moniker already has a table of the requested `game_type`,
the second `create_table` from the owner (or a sysop) now comes
back as a new `type="table_exists"` envelope with the existing
table's metadata and a per-table aggregate `stats` block, instead
of failing with a generic `create_failed` error. Anyone else still
sees `create_failed` so the existence of the table is not leaked;
a duplicate moniker with a **different** game type surfaces as
`code="type_mismatch"` so callers do not silently bind a yahtzee
table to a blackjack moniker.

Wiring:

- `dal/table.py` + `dal/aiosql/table.py`: `create_table` pre-checks
  `casino.__table` for an existing row and returns a sentinel dict
  (`__exists__: True`) so callers can distinguish "already taken"
  from "infrastructure error" without a second `SELECT`. Both
  sync and async paths share a `_row_to_table_dict` mapper.
- `services/table.py`: `TableService.create_table` strips the
  sentinel key and returns `{"success": False, "exists": True,
  "table": existing, "message": …}`. New `get_table_stats`
  passthrough.
- `api/handler.py`: `_handle_create_table` routes the `exists`
  branch to the new `table_exists` envelope, with an owner-or-sysop
  gate (case-insensitive moniker match against `state.moniker`,
  or `state.is_sysop`). Sysop impersonation is fixed — the
  comparison is between actual owner and actual caller, not the
  requested game_type.
- `MessageRouter._bootstrap_casino_config(args)` auto-discovers
  the `casino` section from `args.config_file` (bed's `bed.json`)
  when bed has not wired `args._casino_config` explicitly, so
  door-mode / standalone tests fall back to the built-in defaults
  cleanly.

To make per-table stats meaningful, the settle paths now write
`attrs->'outcome'` / `attrs->'bet_amount'` / `attrs->'net'` on the
`casino.__game` row via a new `dal.game.update_game_attrs` (sync +
aiosql) merge helper:

- **blackjack**: `services/game.py` — surrender reads its forfeit
  fraction from `bed.json` via `casino.config.get_surrender_multiplier`
  (defaults to 0.5, matching the universal casino standard per
  Wizard of Odds / Vegas Advantage). Settle writes
  `outcome` / `bet_amount` / `net` per outcome (blackjack = 1.5x,
  win = 1x, push = 0, loss/bust = -1x, surrender = -1x × multiplier).
- **yahtzee**: `yahtzee/service.py` — writes at end-of-game
  (`outcome = win if net > 0 else loss`).
- **tictactoe**: `tictactoe/service.py` — writes at settle
  (`outcome ∈ {win, loss, draw}`).
- **poker**: in-memory only; `get_table_stats` returns `{}`
  honestly (no fabricated `hands_played: 0`).

Wire payload (game_type-aware stats shape):

```json
{
  "type": "table_exists",
  "moniker": "blackjack-jam",
  "game_type": "blackjack",
  "owner": "jam",
  "min_bet": 10, "max_bet": 1000,
  "location": "NorthAlpha",
  "hidden": false,
  "stats": {
    "hands_played": 12, "wins": 7, "losses": 3, "pushes": 1,
    "blackjacks": 0, "busts": 1, "surrenders": 0, "net": 24
  },
  "message": "blackjack table 'blackjack-jam' already exists; showing stats"
}
```

`CasinoClient.handle_message` renders this with the
`{var:labelcolor}` / `{var:valuecolor}` label/value pattern
established at `yahtzee/play.py:176-253`. Per-game stat keys:
blackjack → `{hands_played, wins, losses, pushes, blackjacks,
busts, surrenders, net}`; slots → `{spins, wins, losses, net}`;
yahtzee / tictactoe → `{hands_played, wins, losses, draws, net}`;
poker → `{}`.

Configuration (per-casino nested layout in `bed.json`):

```json
{
  "casino": {
    "blackjack": {
      "surrender_allowed": "early",
      "surrender_multiplier": 0.5
    }
  }
}
```

`casino.config.get_surrender_multiplier` clamps out-of-range and
garbage values to the `0.5` default, and honors
`surrender_allowed: false` / `"none"` → `0.0`. See the
test_casino_config suite for the full matrix.

Tests:

- `test_blackjack_three_hands.py`: new
  `test_create_duplicate_table_returns_table_exists` exercises
  the owner short-circuit and the type_mismatch branch.
- `test_hidden_tables.py`: pre-existing `dal.table.create_table`
  mocks updated for the new pre-check fetchone.
- `test_casino_config.py` (new): 11 unit tests for
  `get_casino_config` (wiring, fallback, file path, defaults)
  and `get_surrender_multiplier` (honors config, allowed flag,
  clamping, garbage values).
- `test_blackjack_three_hands_bed.py` (new): bed-targeted
  companion; auto-skips when bed is not reachable at
  `ws://127.0.0.1:8765/`. Documented caveat: bed loads casino
  modules at startup, so the daemon must be restarted to pick up
  the new `__exists__` sentinel — without a restart the
  duplicate-table scenario falls back to the unique-constraint
  path on `casino.__bank_table_pkey`.

### casino: move `bootstrap_opencode.sql` into `src/casino/sql/` and add existence guards

The script previously crashed with `No such file or directory` on the
inner `\i 'src/casino/sql/casino.sql'` when invoked from any directory
other than the casino repo root, and on a totally fresh DB (no
`bank` / `engine` schemas) the `ALTER SCHEMA bank OWNER TO opencode`,
`ALTER TABLE bank.__account OWNER TO opencode`, and
`GRANT … ON ALL TABLES IN SCHEMA bank TO opencode` lines produced
roughly 60 cascade errors (`schema "bank" does not exist`,
`relation "bank.__account" does not exist`, etc.) before the
`CREATE EXTENSION IF NOT EXISTS citext` and `\i casino.sql` ever ran.

Three changes:

1. **Moved to `src/casino/sql/`.** The script now lives alongside
   the canonical casino driver (`casino.sql`) and the per-table
   `*.sql` files. Run command becomes:

   ```
   cd casino/src/casino/sql
   psql -d <dbname> -U postgres -f bootstrap_opencode.sql
   ```

   psql CWD must be `casino/src/casino/sql` so the bare `\i casino.sql`
   resolves, and so the inner bare-relative `\i schema.sql`,
   `\i player.sql`, etc. inside `casino.sql` also resolve. **This
   supersedes the run-command note in the prior "replace
   `scripts/opencode.sql` with `scripts/bootstrap_opencode.sql`"
   entry** — that entry described an `scripts/` location and a
   quoted `\i 'src/casino/sql/casino.sql'` path; both are gone.

   No `\cd` machinery is needed: the script and the files it loads
   share a directory, so a single CWD is sufficient.

2. **Existence guards everywhere.** Every per-schema DDL statement
   is wrapped in a `DO $bootstrap$ … LOOP … END LOOP;` block that
   checks `pg_namespace` first, so missing `bank` / `engine`
   schemas no-op cleanly on a totally fresh DB. Table ownership is
   resolved dynamically via `information_schema.tables` rather
   than a hard-coded list, so newly-added tables get picked up
   when the script is re-run. The `bank.setup_constraints()` and
   `engine.setup_member_constraints()` `SECURITY DEFINER` helpers
   are wrapped in a single `DO $helpers$` block that creates each
   function only if its schema exists. The `stats jsonb` migration
   on `casino.__player` is wrapped in a `DO $stats$` block that
   checks both the table and the column.

3. **Idempotent.** Re-running on an already-bootstrapped DB is a
   no-op (all statements either have `IF NOT EXISTS` / `IF EXISTS`
   guards or are inside the DO-block checks). Verified against a
   fresh `bootstrap_smoketest` DB on PostgreSQL 18.6: first run
   applies all schema owners, GRANTs, helper functions, and the
   `stats` column; second run produces no errors.

Caveat: on a totally fresh DB without `bank` / `engine` schemas,
the `\i casino.sql` step still produces FK-cascade errors
(`schema "engine" does not exist` on `__player`, etc.) — that is
intrinsic to the casino driver's design (FKs to
`engine.__member`, `bank.__account`), not something this script
can fix. The documented use case is a DB where
`bbsengine6.startup` has already run; on that DB the cascade
doesn't fire and `bootstrap_opencode.sql` succeeds end-to-end.

### casino: bring `startup.main()` up to bbsengine6 check-module standard

`casino.startup.main()` previously mirrored only the classlist portion
of `bbsengine6.backend.checkbank.main()`. After the recent addition of
`__bank_table` and friends (`f978b1e`), three latent gaps remained:

- The `citext` extension was never installed by `casino.startup`, even
  though `casino.__player.membermoniker` (and the new
  `__bank_player.membermoniker`) use citext columns. Fresh-DB bootstrap
  crashed on the first table creation.
- Schema-level GRANTs came solely from the inline GRANT in
  `src/casino/sql/schema.sql`. If the schema was created by another
  path (manual psql, `bootstrap_opencode.sql`), the privs were never
  re-asserted — non-superuser roles (`web`, `term`, `opencode`) saw no
  `USAGE` on `casino`.
- The 18-entry classlist omitted all 8 bank-related classes
  (`__bank_table`, `bank_table`, `__bank_player`, `bank_player`,
  `__banktransaction`, `banktransaction`, `__tabletransfer`,
  `tabletransfer`). On any DB whose casino schema predated `f978b1e`,
  `INSERT INTO casino.__bank_table` failed with
  `relation "casino.__bank_table" does not exist`.

`casino.startup.main()` now installs `citext` via
`database.extensionavailable`/`extensioninstalled`/`creatextension`,
re-asserts `USAGE[, CREATE] ON SCHEMA casino TO {sysop,web,term,opencode}`
via `database.manage_schema_priv` (hybrid: keeps the inline GRANT in
`schema.sql` so a fresh install works without a prior startup run), and
iterates the full 26-entry classlist in FK-safe order. Migration files
(`hidden_table_migration.sql`, `table_shoe_migration.sql`) are
deliberately skipped — their columns are already in `table.sql:14-15,19`.

### casino: replace `scripts/opencode.sql` with `scripts/bootstrap_opencode.sql`

Renamed and updated:

- `CREATE EXTENSION IF NOT EXISTS citext` is added before the schema
  bootstrap — the previous version crashed the first time it tried to
  create `casino.__player`.
- The trailing 44-line `DO $$ … END $$;` block (old lines 131‑175) that
  inlined a stale copy of the casino schema — wrong `__bank_table`
  columns, missing `__bank_player` / `__banktransaction` /
  `__tabletransfer` / `__slot_spin` / `__log` — is replaced with
  `\i 'src/casino/sql/casino.sql'`, which loads the canonical driver
  (the same driver `casino.startup.main` uses via `importsql`). One
  source of truth for casino schema; a new table added to `casino.sql`
  flows through both paths automatically.
- The `bank.setup_constraints()` and `engine.setup_member_constraints()`
  SECURITY DEFINER helpers and the `casino.__player.stats jsonb`
  migration are preserved verbatim — `scripts/setup_test_db.py` still
  calls the helper functions and seeds the `casino:house` account.

Run command is unchanged in spirit: `psql -d <dbname> -U postgres -f
scripts/bootstrap_opencode.sql`, but must be run from the casino repo
root so the `\i 'src/casino/sql/casino.sql'` path resolves.

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
