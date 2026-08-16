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
