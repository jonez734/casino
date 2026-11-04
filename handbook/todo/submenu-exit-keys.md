# Casino submenu exit keys: Q or X

## Status

Open. Decision needed. The submenus work as they did before the migration.

## What is decided

The casino root menu uses `X` as its exit, with `Q` as an alias. It reads through
`bbsengine6.menu_next.read_menu(mode="key")` with the default protected exit `X`.

The game submenu (`casino/commands/game/lib.py`) and the bank submenu
(`casino/commands/bank/lib.py`) read through `read_menu(mode="key")` too, but they keep `Q` as their
exit: `protected=("Q",)`. Neither offers `X`. Players see `[Q]uit` and press `Q`, as before.

## The open question

Should the game and bank submenus move to the official `X` exit, like the root menu?

- Moving them changes the key shown on screen and the key players press.
- Keeping `Q` means the submenus differ from the root menu.

## What changes if the answer is X

- Option strings and prompts in `game/lib.py` and `bank/lib.py`: `[Q]uit` becomes `[X]it`.
- `default="Q"` becomes `default="X"`, and `protected=("Q",)` is removed, so the default
  protected exit applies.
- Tests in `casino/tests/test_submenu_key_mode.py`: the exit key assertions.
- Any help text or docs that name the key.
