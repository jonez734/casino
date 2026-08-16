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
