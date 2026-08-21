from bbsengine6 import menu_next, register_module, util

from . import lib

__version__ = "202210010112"


def init(args, **kw: dict) -> bool:
    register_module(
        name="casino",
        module_path="casino",
        version=__version__,
        apis={},
    )
    menu_next.register_menu_options(
        "casino.lib",
        menu_next.MenuOption("c", "Connect",       "auth"),
        menu_next.MenuOption("l", "List tables",   "table.list"),
        menu_next.MenuOption("j", "Join table",    "table.join"),
        menu_next.MenuOption("v", "View table",    "table.view"),
        menu_next.MenuOption("w", "Watch table",   "admin.watch"),
        menu_next.MenuOption("u", "Unwatch table", "admin.unwatch"),
        menu_next.MenuOption("g", "Global msg",    "chat.global"),
        menu_next.MenuOption("k", "Bank",          "bank"),
        menu_next.MenuOption("x", "Disconnect",    "auth.disconnect", requires_connected=True),
        menu_next.MenuOption("m", "Maintenance",   "maint.main"),
        menu_next.MenuOption("p", "Play",          "game.play",      requires_seated=True),
    )
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw: dict) -> bool:
    return None


def main(args, **kw):
    util.heading("HEADER")
    lib.runmodule("main", **kw)
    return True
