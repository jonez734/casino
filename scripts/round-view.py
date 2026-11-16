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


def _json_sink(target: str):
    """A sink that writes each message as one JSON line to a file, or to stdout for '-'."""
    import json

    out = sys.stdout if target == "-" else open(target, "a", encoding="utf-8", buffering=1)

    def write(message: dict) -> None:
        # The bearer token is a credential: it is never written to the dump.
        safe = {k: ("<redacted>" if k == "token" else v) for k, v in message.items()}
        out.write(json.dumps(safe, default=str) + "\n")
        out.flush()

    write.close = (lambda: None) if out is sys.stdout else out.close
    return write


def _token_directory() -> str:
    """Bed's token directory (the viewer's token files live beside bed's own)."""
    from bed.tools import _token

    return os.path.dirname(_token.default_token_path())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Live view of blackjack round events (Tk).")
    parser.add_argument("--url", default="ws://localhost:8765/", help="daemon WebSocket (default: %(default)s)")
    parser.add_argument("--table", default="blackjack-x", help="table to watch (default: %(default)s)")
    parser.add_argument("--dump", default=None, metavar="FILE",
                        help="also write every message the window receives to FILE, one JSON object per line "
                             "('-' for stdout)")
    parser.add_argument("--moniker", default="",
                        help="the player to log in as (prompted for when omitted)")
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

    from casino.tk import viewer_login

    token = viewer_login.ensure_token(
        _token_directory(), args.moniker,
        is_usable=lambda t: roundview.token_is_usable(args.url, t, args.table),
    )
    if not token:
        print("round-view: could not log in", file=sys.stderr)
        return 2

    sink = _json_sink(args.dump) if args.dump else None
    window = roundview.build_daemon_window(args.url, title=f"Blackjack round: {args.table}",
                                           token=token, table=args.table, sink=sink)
    window.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
