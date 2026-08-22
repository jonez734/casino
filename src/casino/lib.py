from __future__ import annotations

import argparse
import random
import tkinter as tk
from argparse import Namespace
from typing import Any

# import ttyio5 as ttyio
# import bbsengine5 as bbsengine
from bbsengine6 import bottombar, database, io, member, module, util
from bbsengine6.io import screen as bbsengine6_screen
from bbsengine6.io import terminal as bbsengine6_terminal
from PIL import Image, ImageOps, ImageTk

PACKAGENAME = "casino"

suits = {"H": "{u:heart}", "D": "{u:diamond}", "S": "{u:spade}", "C": "{u:club}"}


class Card:
    def __init__(self, shorthand: str = "", facedown: bool = True, **kwargs: Any) -> None:
        self.shorthand = shorthand
        if shorthand is not None and shorthand != "":
            self.pips: str | None = self.shorthand[:-1] if len(self.shorthand) > 1 else None
            self.suit: str | None = self.shorthand[-1:] if len(self.shorthand) > 0 else None
            self.blank = False
        else:
            self.pips = None
            self.suit = None
            self.blank = True

        self.tkart = None
        self.show = True
        self.facedown = facedown
        self.art = None  # self.getart()

    def __repr__(self) -> str:
        return f"Card({self.shorthand=}, {self.suit=}, {self.pips=} {self.art=} {self.facedown=})"

    def value(self) -> int:
        if self.blank is True:
            return 0

        if self.pips == "A":
            v = 11
        elif self.pips in ("K", "Q", "J"):
            v = 10
        else:
            v = int(self.pips) if self.pips is not None else 0

        suit_char = suits.get(self.suit, "") if self.suit else ""
        io.echo(
            f"Card.value.120: card={self.shorthand} {v=}", level="debug"
        )
        return v

    def isace(self) -> bool:
        return self.pips == "A"


class tkCard(Card):
    def __init__(self, args: Any, **kwargs: Any) -> None:
        super().__init__(args, **kwargs)
        self.artpath = self.getartpath()

    def __repr__(self) -> str:
        return f"tkCard({self.shorthand=}, {self.artpath=}, {self.suit=}, {self.pips=} {self.getart()=} {self.facedown=})"

    def getartpath(self) -> str:
        suitname = "unknown"
        if self.suit is None and self.pips is None:
            artpath = "cards/card-blank-008000.png"
        elif self.facedown is True:
            artpath = "cards/card-back-electricblue.png"
        elif self.suit == "D":
            suitname = "diamonds"
        elif self.suit == "H":
            suitname = "hearts"
        elif self.suit == "S":
            suitname = "spades"
        elif self.suit == "C":
            suitname = "clubs"

        if self.pips == "A":
            short = "ace"
        elif self.pips == "J":
            short = "jack"
        elif self.pips == "Q":
            short = "queen"
        elif self.pips == "K":
            short = "king"
        else:
            short = self.pips if self.pips is not None else "unknown"

        artpath = f"cards/{short}_of_{suitname}.png"
        return artpath

    def getart(self) -> ImageTk.PhotoImage:
        self.artpath = self.getartpath()
        with Image.open(self.artpath) as img:
            self.containedimage = ImageOps.contain(img, (100, 250))
            self.tkart = ImageTk.PhotoImage(self.containedimage)
        return self.tkart


class Hand:
    def __init__(self, label, **kwargs):
        self.id = None
        self.label = label
        #        self.shoe = shoe
        self.playerid = kwargs.get("playerid")
        #        self.cards = []
        self.value = 0
        self.index = 0
        self.cards = []
        self.status_override = None

    def adjustace(self):
        adjust = 0
        for card in self.cards:
            if card.isace() is False:
                continue
            if self.value > 21:
                adjust = 10
                io.echo(f"set adjust to {adjust}", level="debug")
                break
        return adjust

    def calcvalue(self):
        self.value = 0
        for c in self.cards:
            self.value += c.value()

        adjust = 0
        if self.value > 21:
            adjust = self.adjustace()
        return self.value - adjust

    def status(self):
        if self.status_override is not None:
            return self.status_override
        value = self.calcvalue()
        if value > 21:
            return "bust"
        if value == 21:
            if len(self.cards) == 2:
                return "naturalblackjack"
            else:
                return "blackjack"
        return "play"

    def add(self, card, facedown=False):
        card.facedown = facedown
        #        ttyio.echo(f"--> len(self.cards)={len(self.cards)}, self.index={self.index}")
        self.cards.append(card)
        self.index = len(self.cards)
        self.refresh()

    def show(self, hide=True):
        io.echo(f"{self.label}: ", end="")
        for counter, c in enumerate(self.cards):
            if c.suit is None:
                continue
            if (
                len(self.cards) == 2
                and counter == 1
                and self.label == "dealer"
                and hide is True
            ):
                io.echo("{u:solidblock:2} ", end="")
            else:
                io.echo(f"{c.pips}{suits[c.suit]} ", end="")

        io.echo(f" [{self.calcvalue()}]", level="debug")

    def hit(self, shoe):
        """Draw a card from shoe and add to hand."""
        card = shoe.draw()
        self.add(card)
        return card

    def stand(self):
        """Mark hand as standing."""
        self.standing = True

    def refresh(self):
        pass

    def totalpoints(self):
        points = 0
        for card in self.cards:
            points += card.value()
        return points


class tkHand(Hand):
    def __init__(self, text, **kwargs):
        super().__init__(text, **kwargs)

        #    self.tklabels = []
        #    self.images = []

        self.frame = kwargs.get("frame")

        #    ttyio.echo(f"--> tkhand.init: self.frame={self.frame!r}", level="debug")

        self.row = kwargs.get("row", 0)
        self.paddings = kwargs.get("paddings", {})

        self.card_labels = []
        self.points_labels = []
        self.totalpoints_label = None

        #    ttyio.echo(f"--> self.frame={self.frame!r}", level="debug")

        #    self.playerframe = tk.LabelFrame(self, borderwidth=4, relief=tk.GROOVE, text=f"player: {playername}")
        #    self.playerframe.grid(column=0, row=row, **self.paddings)
        #    self.playerframe.configure(font=labelfont)

        #    for x in range(0, 5):
        #      card = self.cards[x]
        ##      card = Card(shortname="4S", blank=False, facedown=False)
        # ttyio.echo(f"lib.tkHand.100: {card!r}", level="debug")
        #      art = card.getart()
        #      label = tk.Label(self.frame, bd=2, relief="solid", padx=20, pady=10)#, image=card.getart())
        #      label.configure(image=art)
        #      label.image = art
        #      label.grid(row=0, column=x)
        #      card.tklabel = label
        #      self.tklabels.append(label)
        self.refresh()

    #    ttyio.echo(f"---> tkHand.120: tklabels={self.tklabels!r}", level="debug")

    def show(self, hide: bool = True) -> None:
        for card in self.cards:
            io.echo(f"{self.label=}: {card=}", level="debug")

    def refresh(self) -> None:
        for label in self.card_labels:
            label.destroy()
        for label in self.points_labels:
            label.destroy()
        if self.totalpoints_label is not None:
            self.totalpoints_label.destroy()

        self.card_labels = []
        self.points_labels = []

        totalpoints = 0
        for x in range(0, 5):
            points = 0
            card = self.cards[x]
            art = card.getart()
            label = tk.Label(self.frame, bd=0, relief="solid", padx=50, pady=10)  # type: ignore[arg-type]
            label.configure(image=art)
            label.image = art  # type: ignore[union-attr]
            label.grid(row=0, column=x, padx=20)
            self.card_labels.append(label)
            points = card.value()
            totalpoints += points

            if points == 0:
                pointslabel = tk.Label(
                    self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10  # type: ignore[arg-type]
                )
            else:
                pointslabel = tk.Label(
                    self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10, text=points  # type: ignore[arg-type]
                )
            pointslabel.grid(row=1, column=x)
            self.points_labels.append(pointslabel)

        if totalpoints > 0:
            self.totalpoints_label = tk.Label(
                self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10, text=totalpoints  # type: ignore[arg-type]
            )
        else:
            self.totalpoints_label = tk.Label(
                self.frame, bd=0, relief=tk.SOLID, padx=50, pady=10
            )

        self.totalpoints_label.grid(row=2, column=0, columnspan=5, sticky=tk.W + tk.E)


class Table:
    def __init__(
        self,
        shoeid: int | None = None,
        casinoid: int | None = None,
        minimumbet: int = 1,
        maximumbet: int = 10,
        bank: int = 0,
    ) -> None:
        self.id: int | None = None
        self.shoeid: int | None = shoeid
        self.casinoid: int | None = casinoid
        self.minimumbet = minimumbet
        self.maximumbet = maximumbet
        self.bank = bank

    def update(self):
        pass

    def insert(self):
        pass

    def show(self):
        io.echo(
            f"table: {self.id=}, {self.casinoid=}, {self.shoeid=}, {self.minimumbet=}, {self.maximumbet=}, {self.bank=}",
            level="debug",
        )
        return


class tkTable(Table):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent


class Shoe:
    def __init__(self, tableid=None, decks=1):
        self.id = None
        self.tableid = tableid
        self.cards = []

        if decks is None:
            return

        for _d in range(0, decks):
            for suit in [
                "S",
                "D",
                "C",
                "H",
            ]:  # {u:spade}", "{u:diamond}", "{u:club}", "{u:heart}" ]:
                for pips in [
                    "A",
                    "K",
                    "Q",
                    "J",
                    "2",
                    "3",
                    "4",
                    "5",
                    "6",
                    "7",
                    "8",
                    "9",
                    "10",
                ]:
                    self.cards.append(
                        Card(shorthand=f"{pips}{suit}", facedown=False, blank=False)
                    )

    def shuffle(self, rounds=1):
        for _x in range(0, rounds):
            io.echo("Shoe.shuffle.100: running..", level="debug")
            random.shuffle(self.cards)
        return

    def show(self):
        if len(self.cards) == 0:
            io.echo("this shoe is empty.")
            return
        for card in self.cards:
            io.echo(f"{card.pips}{card.suit} ", end="")
        io.echo()
        return

    def remove(self, pips, suit):
        for c in self.cards:
            if c.pips == pips and c.suit == suit:
                del c
                return

    def draw(self):
        card = self.cards.pop()
        io.echo(f"shoe.draw.100: {card=}", level="debug")
        return card

    def append(self, card: object = None):
        if card is None:
            return

        self.cards.append(card)
        return


def getcardtablelocations():
    cardtablelocations = [
        "Arnhem - Netherlands",
        "Barcelona - Spain",
        "Birmingham - England",
        "Budapest - Hungary",
        "Helsinki - Finland",
        "Munich - Germany",
        "Sicily - Italy",
        "Oslo - Norway",
        "Vienna - Austria",
        "Cape Town - South Africa",
    ]
    return cardtablelocations


class Casino:
    def __init__(self, args: Namespace | None = None, location: str | None = None, bank: int | None = None, ui: str = "tk") -> None:
        self.location: str | None = location
        self.bank: int | None = bank
        self.attributes = [
            {"name": "location", "type": "location", "default": location},
            {"name": "bank", "type": "int", "default": bank},
        ]
        self.dbh = database.connect(args) if args is not None else None
        for a in self.attributes:
            setattr(self, a["name"], a["default"])

    def __edit(self, rec: dict | None = None) -> dict:
        if rec is None:
            rec = {}
        rec["location"] = io.inputstring("{var:promptcolor}location: {var:inputcolor}", self.location if self.location else "")
        rec["bank"] = io.inputinteger("{var:promptcolor}bank: {var:inputcolor}", self.bank if self.bank else 0)
        return rec

    def add(self):
        self.__edit({})

    def load(self, casinoid):
        pass


class Seat:
    def __init__(self, memberid):
        self.memberid = memberid
        pass


_casino_registry = bottombar.registry_for("casino")
_casino_fragments = []

# Legacy module-level aliases preserved so any external code that reads
# `casino.lib._current_player` / `_current_args` keeps working. They are
# kept in sync with `_casino_registry` by setbottombar().
_current_args = _casino_registry.args
_current_player = _casino_registry.player

# Mirrors the pattern in bbsengine6.ed.common.ui._screen_initialized:
# call io.screen.init() exactly once per process so the scroll region
# (top/bottom margins) is set before any setbottombar() call lands.
# setbottombar() positions text on ``terminal.lines()`` -- without a
# scroll region the bottombar would scroll off the visible area when
# the user types past the bottom of the screen.
_screen_initialized: bool = False


def _casino_player_fragment(**kwargs) -> str:
    if _casino_registry.player is None:
        return ""
    return f"{_casino_registry.player.moniker}"


def _casino_credits_fragment(**kwargs) -> str:
    if _casino_registry.player is None:
        return ""
    return util.pluralize(_casino_registry.player.credits, "credit", "credits")


def _casino_host_fragment(**kwargs) -> str:
    """Right-side fragment: ``"<host>:<port>"`` or ``"direct"``.

    Reads ``args.bed_host`` and ``args.bed_port`` from the cached
    ``_casino_registry.args`` (stashed by :func:`setbottombar`).
    Falls back to the routing defaults (``127.0.0.1:8765``) when the
    args object does not carry the bed routing attributes. Returns
    ``"direct"`` when ``args._backend == "direct"`` so the operator
    can tell at a glance whether the menu is wired to a BED daemon
    or running straight against the local DB.
    """
    args = _casino_registry.args
    if args is None:
        return ""
    if getattr(args, "_backend", None) == "direct":
        return "direct"
    host = getattr(args, "bed_host", "127.0.0.1") or "127.0.0.1"
    port = int(getattr(args, "bed_port", 8765) or 8765)
    return f"{host}:{port}"


def _register_casino_fragments() -> None:
    for fn in (
        _casino_host_fragment,
        _casino_player_fragment,
        _casino_credits_fragment,
    ):
        if fn not in _casino_fragments:
            bottombar.register_bottombar_fragment(fn)
            _casino_fragments.append(fn)


def _unregister_casino_fragments() -> None:
    for fn in _casino_fragments:
        bottombar.unregister_bottombar_fragment(fn)
    _casino_fragments.clear()


def _ensure_screen_initialized() -> None:
    """Call ``io.screen.init()`` exactly once per process.

    Mirrors :func:`bed.tools.bank._ensure_screen_initialized` and
    :func:`bbsengine6.ed.common.ui.init_screen`. ``screen.init()``
    sets the terminal scroll region (top/bottom margins) so the bottom
    bar stays parked on the last line instead of scrolling off when
    output overflows. setbottombar() positions text on the last line,
    so calling it before screen.init() is a no-op (the bar would be
    drawn but immediately scrolled away on the next line of output).
    """
    global _screen_initialized
    if not _screen_initialized:
        bbsengine6_screen.init()
        _screen_initialized = True


def _clear_bottombar() -> None:
    """Wipe the bottom row so we don't leak the bar past menu() exit.

    Mirrors the cleanup echo in ``bed/src/bed/tools/bank.py`` and
    ``empyre/__main__.py``: save the cursor, jump to
    ``(terminal.height(), 0)``, erase the line, reset attributes, then
    restore the cursor.
    """
    io.echo(
        f"{{savecursor}}{{curpos:{bbsengine6_terminal.height()},0}}"
        f"{{el}}{{reset}}{{restorecursor}}"
    )


def setbottombar(args, buf, **kwargs) -> None:
    global _current_args, _current_player
    player = kwargs.get("player")
    pool = kwargs.get("pool")
    _ensure_screen_initialized()
    # Stash on the per-package registry and on the legacy module globals
    # so any code that still reads `_current_player` / `_current_args`
    # continues to work.
    _casino_registry.set_context(args=args, player=player, pool=pool)
    _current_args = _casino_registry.args
    _current_player = _casino_registry.player
    bottombar.setbottombar(args, buf, player=player, pool=pool)
    _register_casino_fragments()
    return


# @since 20220815
def setarea(args: Namespace, left: str, player: Any = None) -> None:
    def right() -> str:
        currentmember = member.getcurrent(args)
        if currentmember is None:
            return ""
        rightbuf = f"| {currentmember['moniker']} | {util.pluralize(currentmember['credits'], 'credit', 'credits')}"
        if args.debug is True:
            rightbuf += " | debug"
        return rightbuf

    io.screen.setbottombar(left, right)


class Player:
    def __init__(self):
        self.memberid = None
        self.status = "active"
        self.lastvisit = "now()"
        self.tokens = 0
        self.stats = {}

    def incstat(self, game, stat):
        if game not in self.stats:
            self.stats[game] = {}

        if stat not in self.stats[game]:
            self.stats[game][stat] = 0
        self.stats[game][stat] += 1
        return


class CasinoPlayer:
    """Door-mode player facade.

    Mirrors the duck-typed attrs the WS-client ``CasinoClient`` exposes
    (``moniker``, ``credits``, ``current_table_moniker``,
    ``current_table_game_type``, ``connected``) so the visibility
    filter in :func:`casino.menu_lib.visible_options` works against
    either object without branching.

    Construction idempotently materializes the matching
    ``casino.__player`` row via
    :func:`casino.services.player.ensure_casino_player` so the bottombar
    (``_casino_credits_fragment``), the stats menu
    (``casino.menu.show_player_stats``), and the table-seating filter
    (``_refresh_seat``) all see real values from the first frame.
    """

    def __init__(self, args, membermoniker=None, pool=None):
        self.args = args
        self.pool = pool
        self.moniker = membermoniker
        # Default credits/stat/lastplayed; ``ensure_casino_player``
        # below overwrites ``credits`` and ``lastplayed`` from the row
        # so the bottombar shows real numbers, not the placeholder.
        self.credits = 1000
        self.stats = {}
        self.lastplayed = None
        # Visibility state, populated lazily by ``_refresh_seat`` so
        # the door-mode menu in ``casino.main`` can mirror the WS-client
        # menu in ``casino.client.menu`` (which reads the same attrs on
        # ``CasinoClient``).
        self.current_table_moniker: str | None = None
        self.current_table_game_type: str | None = None
        # WS-connection state for the door-mode ``casino.main`` loop:
        # ``None`` before ``auth.connect`` succeeds, ``True`` after. The
        # ``requires_connected`` gate in ``casino.menu_lib`` uses this
        # to hide the ``[X] Disconnect`` option until a connection is
        # open.
        self.connected: bool = False
        self._ensure_player_row()
        self._load()

    def _ensure_player_row(self):
        """Idempotently create the casino.__player row for this member.

        Mirrors the WS-client path (``PlayerService.authenticate``),
        which also calls ``ensure_casino_player`` on every successful
        login. After this call, the row is present and ``self.credits``
        / ``self.lastplayed`` / ``self.stats`` are populated from the
        row so the bottombar and stats menu render real values on the
        first frame. ``audit=True`` emits one debug-level echo so a
        sysop running ``casino --debug`` can see which members were
        auto-materialized.

        Best-effort: a DB error is swallowed and the placeholder
        attrs (``credits=1000``, ``stats={}``, ``lastplayed=None``)
        stay so the menu still renders. Commands that need a real
        row will error at their own access gate.
        """
        try:
            from .dal import player as dal_player
            from .services.player import ensure_casino_player

            row = ensure_casino_player(
                self.args, self.moniker, pool=self.pool, audit=True
            )
            if row is not None:
                self.lastplayed = row.get("lastplayed")
                self.credits = dal_player.get_player_balance(
                    self.args, self.moniker
                )
                self.stats = dal_player.get_player_stats(
                    self.args, self.moniker
                )
        except Exception:
            pass

    def _load(self):
        self._refresh_seat()

    def _refresh_seat(self):
        """Re-query the DB for the player's current table.

        Joins ``casino.__map_cardtable_player`` (player → table) with
        ``casino.__table`` (table → type) to recover both the table
        moniker and its ``game_type``. Sets
        ``current_table_moniker`` and ``current_table_game_type`` on
        the player so the menu visibility filter in
        ``casino.main`` can hide seat-gated options when the player
        isn't at a table.

        Best-effort: any DB error is swallowed and the attrs stay
        ``None`` so the menu can still render. Commands that need
        an actual seat (e.g. ``game.bet``) will error at their own
        access gate if misused.
        """
        if not (self.pool and self.moniker):
            return
        try:
            from bbsengine6 import database
            with database.connect(self.args) as conn, database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        "SELECT m.tablemoniker, t.type AS game_type "
                        "FROM $casino.__map_cardtable_player m "
                        "JOIN $casino.__table t ON t.moniker = m.tablemoniker "
                        "WHERE m.playermoniker = :moniker LIMIT 1",
                        moniker=self.moniker,
                    )
                )
                row = cur.fetchone()
                if row:
                    self.current_table_moniker = row["tablemoniker"]
                    self.current_table_game_type = row["game_type"]
                else:
                    self.current_table_moniker = None
                    self.current_table_game_type = None
        except Exception:
            self.current_table_moniker = None
            self.current_table_game_type = None

    def save(self):
        pass


def buildargs(args: Namespace | None = None, **kwargs: Any) -> argparse.ArgumentParser:
    from . import _version as casino_version

    parser = argparse.ArgumentParser(
        prog="casino",
        description=(
            "Casino CLI: blackjack, slots, poker, yahtzee, tictactoe. "
            "Defaults to the bed WebSocket; pass --direct for door mode."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"casino {casino_version.__version__}",
    )
    parser.add_argument("--verbose", action="store_true", dest="verbose")
    parser.add_argument("--debug", action="store_true", dest="debug")

    defaults = {
        "databasename": "zoid6",
        "databasehost": "localhost",
        "databaseuser": None,
        "databaseport": 5432,
        "databasepassword": None,
    }
    database.buildarggroup(parser, defaults)

    from . import _routing
    _routing.build_client_args(parser)

    return parser


def runmodule(args: Namespace | None, modulename: str, **kwargs: Any) -> Any:
##    io.echo(f"{args=} {modulename=}", level="debug")
    package = kwargs.pop("package", "casino")
    return module.runmodule(args, f"{package}.{modulename}", **kwargs)
