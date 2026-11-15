#!/usr/bin/env python3
"""Open the Tk round window: a live view of a blackjack round's events (slice 6).

Usage (from the casino checkout, with the tk extra installed):

    python3 scripts/round-view.py [--table MONIKER]

It needs a display (DISPLAY set, or run it from a desktop session). It builds the same GameService the
daemon uses and shows the events it publishes in the window as they happen. Close the window to exit.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Live view of blackjack round events (Tk).")
    parser.add_argument("--table", default="blackjack-x", help="table moniker to watch (default: %(default)s)")
    args = parser.parse_args(argv)

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or sys.platform == "win32"
            or sys.platform == "darwin"):
        print("round-view: no display. Run this from a desktop session, or set DISPLAY.", file=sys.stderr)
        return 2

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("round-view: tkinter is not installed for this Python.", file=sys.stderr)
        return 2

    from types import SimpleNamespace

    from casino.services.game import GameService
    from casino.tk import roundview

    # The service the daemon uses: built from the same args the router gets. Events are published by the
    # service's own methods, so the window shows what a running daemon publishes in this process.
    service = GameService(SimpleNamespace(), pool=None)
    window = roundview.build_window(service, title=f"Blackjack round: {args.table}", table=args.table)
    window.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
