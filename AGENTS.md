# casino — agent guidance

Notes accumulated from debugging sessions. Read before investigating
echo / color / markup issues in this codebase.

## When bbsengine6 markup shows up as literal text

The first thing to check is whether `io.echo()` was actually called.
Python's `print()` bypasses the entire echo pipeline, so any
`{name}` / `{{name}}` / `{var:name}` markup in the string lands on
the terminal verbatim.

Quick grep for the anti-pattern in this repo:

```sh
grep -rn "print(.*render_ascii\|print(.*\.echo\b" casino/src/
```

The correct pattern is `io.echo(rendered_string)` — never `print()`
for anything carrying echo markup. The fix history has the
slots smoke spin and door-mode loop as canonical examples (see
commits around `11c2663`).

Related f-string footgun: in `f"...{{name}}..."` the `{{` escapes
to `{` and `io.echo` interprets the result as a variable. In a
plain `"...{{name}}..."` (no `f` prefix) the `{{` is literal and
echo leaves it as-is. Anywhere echo markup is interpolated, double-
check whether the surrounding string is an f-string.

## Stale `__pycache__` can mask a fix that's already in HEAD

A `.pyc` mtime older than the corresponding `.py` mtime can cause
Python to load the cached bytecode even after a source fix. If a
bug persists after editing, before suspecting the edit again:

```sh
find casino -name __pycache__ -path "*slots*" -exec rm -rf {} +
```

Then re-run the relevant tests. This came up in the
`render_ascii` investigation where the source was already correct
in HEAD but a stale pyc produced literal `{sym.color}` text.

## Consistent color-tag vocabulary across modules

Use the established `{var:<name>}` and `{level.<name>}` tags — not
loose single-word tags. The slots module has been migrated; do not
revert to bare `{title}`, `{normal}`, `{success}`, `{error}`.

| Use | Instead of | Established at |
|---|---|---|
| `{var:titlecolor}` | `{title}` | blackjack/play.py:20,100,103; yahtzee/play.py:252 |
| `{var:normalcolor}` | `{normal}` | blackjack/play.py:32,50; yahtzee/play.py:177 |
| `{level.error}` | `{error}` (no `level.` prefix) | blackjack/play.py:32,47,56,85; menu.py:32 |
| `{level.ok}` | `{success}` | blackjack/play.py:50,109 |
| `{var:labelcolor}` + `{var:valuecolor}` | bare text | yahtzee/play.py:176-253 stat-display pattern |

When displaying label/value pairs (e.g. `target RTP: 0.92`), wrap
the label in `{{var:labelcolor}}` and the value in
`{{var:valuecolor}}`. The f-string double-brace escape
(`{{var:labelcolor}}` → `{var:labelcolor}`) is what `io.echo`
interprets; never write `{var:labelcolor}` directly inside an
f-string without the double braces.

## Reset attributes before rendering the slot grid

The slot machine draws a 5x3 ACS box-drawing grid via
`lib.render_ascii()`. Per-symbol color tags open and close cleanly,
but no `{/all}` is emitted, so any leftover attributes from prior
echoes leak into the grid. Always precede the box render with
`io.echo("{/all}")`:

```python
io.echo("{/all}")
io.echo(render_ascii(result))
```

This applies in both `__main__.py:_smoke_spin` (smoke spin) and
`play.py:run_one_spin` (door-mode loop).

## Reset ACS at the end of `render_ascii`

`render_ascii()` ends with `{lrcorner}`, which leaves the terminal
in DEC graphics mode (ACS on). Any raw stdout write that follows
(e.g. `print()` in `_smoke_spin` / `_run_door` / `_run_demo`) is
then rendered as DEC glyphs — i.e. garbled.

`render_ascii()` already appends a trailing `{/all}` to its
returned string; that token routes through `_handle_command`'s
unconditional `_acs_off()` (`ESC ( B`) and then `_handle_slashall`
(`ESC [ 0 m`), so the terminal is back in the default character
set by the time `io.echo(render_ascii(result))` returns. Do not
remove that trailing `{/all}`; the regression test
`test_render_ascii_ends_with_acs_off` in
`tests/test_slots_unit.py` pins the contract.

When emitting text after the box render, prefer `io.echo()` over
`print()`: `print()` bypasses the echo pipeline entirely, so even
with the trailing reset, a `print()` call that follows another
`print()` (which is itself preceded by the box render) will not
see any leftover state from `io.echo` runs — but it also won't
benefit from any color tag expansion, and a future regression
that re-introduces an ACS leak would not be guarded.

## Inline `io.inputchoice()` prompts need `{f6}` between options

The WS-client has two call sites where multiple `[X]label`
fragments are joined into a single `io.inputchoice()` prompt
string (see `SPEC.md` §6.1):

- `src/casino/client/menu.py:menu()` — main casino_client prompt.
- `src/casino/client/casino_client.py:cmd_bank_menu()` — bank
  submenu.

`io.inputchoice` writes the prompt string verbatim via `io.echo`
machinery, so any `\n` inside the prompt is meaningless — there
is no implicit separator between concatenated fragments. Use
`"{f6}".join(...)` (or insert `"{f6}"` between entries in a
hand-built string), not `"".join(...)`. Without `{f6}` the entire
option list renders on one horizontal line and is hard to read.

Door-mode `mainmenuhelp` (`main.py:88-103`) and the F1 help
callback (`client/menu.py:_render_help`) are not affected: both
loop and call `io.echo()` per option, and `io.echo` appends `\n`
via `end=ECHO_END`. The inline-prompt case is the one that needs
the explicit `{f6}`.

Regression guard: `tests/test_menu_inline_prompt.py` pins the
seam count (`len(visible) - 1` `{f6}` markers for the main
prompt; 7 for the bank submenu).
