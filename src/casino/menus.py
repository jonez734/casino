"""casino/menus.py

Menu registries for casino. Each menu is a ``bbsengine6.menu_next.Registry``
of ``MenuOption`` items, scoped by registrar name.
"""

from bbsengine6.menu_next import MenuOption, Registry

#: The casino door menu. Registrar scope ``"casino.lib"``.
MAIN_MENU = Registry()

CASINO_LIB_SCOPE = "casino.lib"

_CASINO_LIB_OPTIONS = (
    MenuOption("c", "Connect",       "auth"),
    MenuOption("l", "List tables",   "table.list"),
    MenuOption("j", "Join table",    "table.join"),
    MenuOption("v", "View table",    "table.view"),
    MenuOption("w", "Watch table",   "admin.watch"),
    MenuOption("u", "Unwatch table", "admin.unwatch"),
    MenuOption("g", "Global msg",    "chat.global"),
    MenuOption("k", "Bank",          "bank"),
    MenuOption("x", "Disconnect",    "auth.disconnect", requires_connected=True),
    MenuOption("m", "Maintenance",   "maint.main"),
    MenuOption("p", "Play",          "game.play",      requires_seated=True),
)


def register_casino_lib_options() -> None:
    """Add the ``casino.lib`` options to ``MAIN_MENU``. Safe to call again:
    each letter is a key, so a repeat call replaces rather than duplicates."""
    for opt in _CASINO_LIB_OPTIONS:
        MAIN_MENU.add(opt.letter, opt, scope=CASINO_LIB_SCOPE)
