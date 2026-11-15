#!/usr/bin/env python3
"""Open the Tk round window: a live view of a blackjack round's events (slice 6).

Usage (from the casino checkout, with the tk extra installed):

    python3 scripts/round-view.py [--url ws://localhost:8765/]

It needs a display (DISPLAY set, or run it from a desktop session). It connects to a running casino daemon
(bed's WebSocket, the same one the TUI uses) and shows that table's state as it changes. It only reads;
it cannot change a table. Close the window to exit.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Live view of blackjack round events (Tk).")
    parser.add_argument("--url", default="ws://localhost:8765/", help="daemon WebSocket (default: %(default)s)")
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

    from casino.tk import roundview

    window = roundview.build_daemon_window(args.url, title="Blackjack round")
    window.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
