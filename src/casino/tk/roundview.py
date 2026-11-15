"""The Tk round view: a window that shows a round's events as they happen (slice 6, Tk front end).

The model (RoundViewModel) reads the shared GameService through its own subscription and turns each event
into one line. It knows nothing of Tk, so it is tested without a display. start_polling schedules the model's
poll on a Tk window's own loop (``after``), so domain code never runs on another thread.
"""

from __future__ import annotations

from typing import Any

from bbsengine6.seam.kinds import LAGGED_KIND


def _line(event) -> str:
    kind = event.kind
    p = event.payload
    if kind == "bet_placed":
        return f"{event.moniker} bet {p['amount']}"
    if kind == "card_dealt":
        return f"dealt {p['card']}"
    if kind == "hand_settled":
        net = int(p.get("net", 0))
        sign = "+" if net > 0 else ""
        return f"{event.moniker} hand {p['hand_id']}: {p['result']}, net {sign}{net}"
    if kind == "round_expired":
        return "round expired"
    if kind == LAGGED_KIND:
        return f"missed {p['missed']} events (fell behind)"
    return f"{kind}"


class RoundViewModel:
    """The lines the window shows, built from a subscription to a GameService's events."""

    def __init__(self, service: Any, *, table: str | None = None) -> None:
        self._service = service
        self._sub = service.subscribe_events()
        self._table = table  # None shows every table
        self.lines: list[str] = []

    def _handle(self, event) -> None:
        self.lines.append(_line(event))

    def poll(self) -> list[str]:
        """Read what is new since the last poll, add it to the window's lines, and return just the new lines."""
        new = []
        for event in self._service.read_events(self._sub):
            if self._table is not None and event.scope != self._table:
                continue
            line = _line(event)
            self.lines.append(line)
            new.append(line)
        return new


def start_polling(window: Any, model: RoundViewModel, *, interval_ms: int = 200) -> None:
    """Poll the model on the window's own loop, every ``interval_ms``. The first poll is scheduled, not run."""

    def tick() -> None:
        model.poll()
        window.after(interval_ms, tick)

    window.after(interval_ms, tick)


def build_window(service: Any, *, title: str = "Blackjack round", table: str | None = None) -> Any:
    """A tkinter window that shows the round's events as they arrive. Needs a display.

    Returns the window; call its ``mainloop()`` to run it. The window owns a RoundViewModel and polls it on
    its own loop with start_polling, so the service is only ever read from the window's thread.
    """
    import tkinter as tk
    from tkinter import scrolledtext

    model = RoundViewModel(service, table=table)
    window = tk.Tk()
    window.title(title)
    text = scrolledtext.ScrolledText(window, width=60, height=18, state="disabled")
    text.pack(fill="both", expand=True)

    def refresh() -> None:
        new = model.poll()
        if new:
            text.configure(state="normal")
            for line in new:
                text.insert("end", line + "\n")
            text.configure(state="disabled")
            text.see("end")

    def tick() -> None:
        refresh()
        window.after(200, tick)

    window.after(200, tick)
    window.model = model  # keep the model reachable for callers and tests
    return window


class WireRoundViewModel:
    """The lines the window shows, built from the daemon's game_state messages (a WebSocket client).

    This is the viewer's real source: the daemon already sends the table's state to every client, so the
    window needs no second game service and works across processes. Lines follow the TUI's wording.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []

    def feed(self, message: dict) -> None:
        if message.get("type") != "game_state":
            return
        hand = message.get("player_hand") or []
        if hand:
            self.lines.append(f"Your hand: {' '.join(hand)} [{message.get('player_total', 0)}]")
        dealer = message.get("dealer_hand") or []
        if dealer:
            self.lines.append(f"Dealer: {' '.join(dealer)} [{message.get('dealer_total', 0)}]")
        settled = message.get("round_settled")
        if settled:
            for o in settled.get("outcomes", []):
                if o.get("text"):
                    self.lines.append(f"Result ({o.get('player', '?')}): {o['text']}")
                else:
                    self.lines.append(
                        f"Result ({o.get('player', '?')}): {o.get('result', '?')}, net {o.get('net', 0)}"
                    )
            self.lines.append(f"Round net: {settled.get('net', 0)}")


async def read_daemon(url: str, model: "WireRoundViewModel", on_update) -> None:
    """Read the daemon's messages from ``url`` and feed the model; call ``on_update`` after each one.

    Runs on its own asyncio loop (see start_daemon_reader). It only reads: nothing is sent to the daemon,
    so the viewer cannot change a table.
    """
    import json

    import websockets

    async with websockets.connect(url) as ws:
        async for raw in ws:
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            model.feed(message)
            on_update()


def start_daemon_reader(url: str, model: "WireRoundViewModel", on_update) -> "threading.Thread":
    """Run read_daemon on a background thread with its own loop. Returns the started thread."""
    import asyncio
    import threading

    def run() -> None:
        asyncio.run(read_daemon(url, model, on_update))

    thread = threading.Thread(target=run, name="casino-round-view", daemon=True)
    thread.start()
    return thread


def build_daemon_window(url: str, *, title: str = "Blackjack round") -> Any:
    """A Tk window that shows the daemon's table state as it changes. Needs a display.

    The reader thread feeds the model; the window copies new lines into its text widget from its own loop
    (after), so Tk is never touched from the reader's thread.
    """
    import queue
    import tkinter as tk
    from tkinter import scrolledtext

    model = WireRoundViewModel()
    pending: "queue.Queue[None]" = queue.Queue()
    window = tk.Tk()
    window.title(title)
    text = scrolledtext.ScrolledText(window, width=60, height=18, state="disabled")
    text.pack(fill="both", expand=True)
    shown = [0]

    def on_update() -> None:
        pending.put(None)  # called from the reader thread; only queues work for the Tk thread

    def refresh() -> None:
        if pending.empty():
            return
        while not pending.empty():
            pending.get_nowait()
        new = model.lines[shown[0]:]
        shown[0] = len(model.lines)
        if new:
            text.configure(state="normal")
            for line in new:
                text.insert("end", line + "\n")
            text.configure(state="disabled")
            text.see("end")

    def tick() -> None:
        refresh()
        window.after(200, tick)

    window.after(200, tick)
    start_daemon_reader(url, model, on_update)
    window.model = model
    return window
