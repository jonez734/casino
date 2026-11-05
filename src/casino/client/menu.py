# casino/client/menu.py
# Main menu for CasinoClient, read with bbsengine6.menu_next.read_menu.
#
# The menu is a list of word-keyed MenuOptions. Typed text may be a key or an
# alias, and tab completes the enabled ones. Each entry names the command
# package that owns it (module_path) and the access op it is gated by (op), so
# every prompt re-checks it through that package's access() with the client.

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsengine6 import io, module, util
from bbsengine6.menu_next import Choice, MenuOption, menu_entries, read_menu, visible_options

from .. import host as _host
from .registry import get_client

if TYPE_CHECKING:
    from .casino_client import CasinoClient


_TABLE = "casino.commands.table"
_GAME = "casino.commands.game"
_POKER = "casino.commands.poker"
_ADMIN = "casino.commands.admin"
_TTT = "casino.commands.tictactoe"

_BLACKJACK = frozenset({"blackjack"})
_BLACKJACK_POKER = frozenset({"blackjack", "poker"})
_POKER_ONLY = frozenset({"poker"})
_TTT_ONLY = frozenset({"tictactoe"})


def _sub(letter: str, label: str, module_path: str | None = None, **kw) -> MenuOption:
    return MenuOption(letter, label, module_path, **kw)


# Blackjack and bet are game subcommands, reached by top-level aliases.
_GAME_SUBS = {
    "hit": _sub("hit", "Hit     (take another card)", _GAME, op="hit",
                requires_seated=True, allowed_game_types=_BLACKJACK),
    "stand": _sub("stand", "Stand   (hold your hand)", _GAME, op="stand",
                  requires_seated=True, allowed_game_types=_BLACKJACK),
    "double": _sub("double", "Double  (double down)", _GAME, op="double",
                   requires_seated=True, allowed_game_types=_BLACKJACK),
    "split": _sub("split", "Split   (split a pair)", _GAME, op="split",
                  requires_seated=True, allowed_game_types=_BLACKJACK),
    "bet": _sub("bet", "Bet     (place a wager)", _GAME, op="bet",
                requires_seated=True, allowed_game_types=_BLACKJACK_POKER),
}

_TTT_SUBS = {
    "quickplay": _sub("quickplay", "Quick play (tictactoe, vs AI)", _TTT, op="quickplay"),
    "join": _sub("join", "Join    (join tictactoe as 'O')", _TTT, op="join",
                 requires_seated=True, allowed_game_types=_TTT_ONLY),
}

_ADMIN_SUBS = {
    "watch": _sub("watch", "Watch a table's events and chat", _ADMIN,
                  op="watch_table", sysop_only=True),
    "unwatch": _sub("unwatch", "Stop watching a table", _ADMIN,
                    op="stop_watching", sysop_only=True),
    "kick": _sub("kick", "Remove a player from a table", _ADMIN,
                 op="kick_player", sysop_only=True),
}

def _table_parser(name: str):
    """The argument parser for one table subcommand, from the table package's buildargs.

    ``create`` and ``join`` take optional values; the other subcommands take none.
    """
    from casino.commands import table as table_pkg

    root = table_pkg.buildargs(None)
    for action in root._actions:
        if getattr(action, "choices", None) and name in action.choices:
            sub_parser = action.choices[name]
            sub_parser.prog = f"table {name}"
            return sub_parser
    return None


def _play_verb_sub(verb: str, label: str) -> MenuOption:
    """A table play verb, seat-gated, and gated to the table types whose game declares it.

    The allowed types come from the game packages' TABLE_VERBS, the same declaration the table
    dispatch reads, so the menu and the dispatch agree without a second list here.
    """
    from casino.commands.table import play as _play

    types = frozenset(t for t, verbs in _play.PLAY_VERBS.items() if verb in verbs)
    return _sub(verb, label, _TABLE, op=verb, requires_seated=True, allowed_game_types=types)


# Play verbs on the seated table, reached as ``table <verb>`` and as top-level aliases.
_TABLE_PLAY_SUBS = {
    "bet": _play_verb_sub("bet", "Bet     (place a wager)"),
    "hit": _play_verb_sub("hit", "Hit     (take another card)"),
    "stand": _play_verb_sub("stand", "Stand   (hold your hand)"),
    "double": _play_verb_sub("double", "Double  (double down)"),
    "split": _play_verb_sub("split", "Split   (split a pair)"),
    "play": _play_verb_sub("play", "Play    (blackjack: take the next action)"),
    "check": _play_verb_sub("check", "Check   (poker: pass the action)"),
    "call": _play_verb_sub("call", "Call    (poker: match the bet)"),
    "raise": _play_verb_sub("raise", "Raise   (poker: raise the bet)"),
    "fold": _play_verb_sub("fold", "Fold    (poker: give up the hand)"),
    "allin": _play_verb_sub("allin", "All-in (poker: bet everything)"),
    "start": _play_verb_sub("start", "Start   (poker: deal the hand)"),
    "move": _play_verb_sub("move", "Move    (tictactoe: place a mark, cell 0-8)"),
    "resign": _play_verb_sub("resign", "Resign  (tictactoe: forfeit the game)"),
}

_TABLE_SUBS = {
    "list": _sub("list", "List open tables", _TABLE, op="list_tables",
                 parser=_table_parser("list")),
    "create": _sub("create", "Create a table", _TABLE, op="create_table",
                   parser=_table_parser("create")),
    "join": _sub("join", "Join a table", _TABLE, op="join_table",
                 parser=_table_parser("join")),
    "update": _sub("update", "Update a table (owner or sysop)", _TABLE, op="update_table",
                   parser=_table_parser("update")),
    "leave": _sub("leave", "Leave the current table", _TABLE, op="leave_table",
                  requires_seated=True, parser=_table_parser("leave")),
    "view": _sub("view", "View a table", _TABLE, op="view_table",
                 parser=_table_parser("view")),
}

_OPTIONS_SPEC = (
    MenuOption("table", "Table   (list, create, join, update, leave, view, play verbs)",
               _TABLE, op="list_tables", subcommands={**_TABLE_SUBS, **_TABLE_PLAY_SUBS},
               aliases=tuple(_TABLE_PLAY_SUBS),
               alias_subcommand={verb: verb for verb in _TABLE_PLAY_SUBS}),
    MenuOption("bank", "Bank    (open the bank submenu)", "casino.commands.bank", op="balance"),
    MenuOption("channels", "Channels (open the channel submenu)", None),
    MenuOption("chat", "Chat    (global or table chat)", "casino.commands.chat", op="chat"),
    MenuOption("message", "Message (send a direct message)", None),
    MenuOption("admin", "Admin   (watch, unwatch, kick)", _ADMIN, op="watch_table",
               sysop_only=True, subcommands=_ADMIN_SUBS),
    MenuOption("tictactoe", "Tictactoe (quick play, move, join, resign)", _TTT,
               op="quickplay", subcommands=_TTT_SUBS,
               aliases=("ttt",),
               alias_subcommand={"ttt": "quickplay"}),
    MenuOption("game", "Game    (bet, hit, stand, double, split)", _GAME,
               op="bet", subcommands=_GAME_SUBS),
    MenuOption("quit", "Quit", None),
)


def _check_top_level_names(spec) -> None:
    """Refuse a spec in which a top-level name or alias is used twice.

    An alias that shares a name with another top-level command would silently shadow it. Failing here, at
    menu build, names both so the clash is fixed at the source.
    """
    seen: dict[str, str] = {}
    for opt in spec:
        for name in (opt.letter, *opt.aliases):
            if name in seen and seen[name] != opt.letter:
                raise ValueError(
                    f"top-level name {name!r} is used by both {seen[name]!r} and {opt.letter!r}"
                )
            seen[name] = opt.letter


_check_top_level_names(_OPTIONS_SPEC)

_DEFAULT = "quit"


def _checker(client: "CasinoClient | None"):
    """``check(module_path, op)`` bound to ``client``.

    The owning package's ``access()`` decides, with the client passed as
    ``client``. A missing client denies everything that names a package.
    """
    args = getattr(client, "args", None)

    def check(module_path: str, op: str) -> bool:
        if client is None:
            return False
        if args is None:
            # No bed args means there is no access policy to ask. The spec's own
            # gates (seat, game type, sysop) still apply.
            return True
        return module.check(args, module_path, op, package=module_path, client=client) is True

    return check


def _visible_options(client: "CasinoClient | None"):
    """``(key, label)`` for the options the client may pick now."""
    return [
        (opt.letter, opt.label)
        for opt in visible_options(_OPTIONS_SPEC, client, check=_checker(client))
    ]


def _render_help(client: "CasinoClient | None" = None, **kwargs) -> None:
    """F1/HELP callback. A sysop sees every command; entries that are not
    available now are dimmed with ``menu.item.disabled``.
    """
    client = client or get_client()
    util.heading("casino_client")
    sysop = bool(getattr(client, "is_sysop", False))
    for opt, enabled in menu_entries(_OPTIONS_SPEC, client, check=_checker(client)):
        if not enabled and not sysop:
            continue
        style = "{var:menu.item.enabled}" if enabled else "{var:menu.item.disabled}"
        io.echo(f"{{{style}}}[{opt.letter.upper()}]{{/all}} {opt.label}")


def menu(client: "CasinoClient | None" = None, **kwargs) -> Choice:
    """Read one command from the main menu and return it as a :class:`Choice`.

    ``Choice.key`` is the canonical key, so ``hit`` comes back as ``"game"``
    with ``Choice.subcommand == "hit"``. ``Choice.args`` carries any parsed
    arguments.
    """
    client = client or get_client()
    status = f"{{var:promptcolor}}[{client.moniker}] Balance: {client.balance}"
    if client.current_table_moniker:
        status += f" Table: {client.current_table_moniker}"
    prompt = status + "{f6}{var:promptcolor}casino_client: {var:inputcolor}"
    return read_menu(
        prompt,
        _OPTIONS_SPEC,
        state=client,
        check=_checker(client),
        default=_DEFAULT,
        help=lambda **kw: _render_help(client=client, **kw),
        reader=_host.read_line,
    )
