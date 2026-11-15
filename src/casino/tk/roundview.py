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
