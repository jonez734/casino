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


def _default_token_path() -> str:
    """The viewer's token file for this terminal, so it does not share a token with another client.

    The name is ``round-view.<tty>.token`` in bed's token directory. The tty naming is done here, not imported
    from bed, so the viewer works against any installed bed. Log in to the file once with
    ``bed auth login --token-file <this path>``; the viewer reads it and never writes it.
    """
    import os

    from bed.tools import _token

    directory = os.path.dirname(_token.default_token_path())
    try:
        device = os.ttyname(sys.stdin.fileno())
    except OSError:
        device = ""
    if not device:
        return os.path.join(directory, "round-view.token")
    name = device.replace("/dev/", "", 1).replace("/", "_")
    return os.path.join(directory, f"round-view.{name}.token")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Live view of blackjack round events (Tk).")
    parser.add_argument("--url", default="ws://localhost:8765/", help="daemon WebSocket (default: %(default)s)")
    parser.add_argument("--table", default="blackjack-x", help="table to watch (default: %(default)s)")
    parser.add_argument("--dump", default=None, metavar="FILE",
                        help="also write every message the window receives to FILE, one JSON object per line "
                             "('-' for stdout)")
    parser.add_argument("--token-file", default=None,
                        help="bed token file (default: the one 'bed auth login' writes)")
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

    token_path = args.token_file or _default_token_path()
    token = roundview.read_token(token_path)
    if not token:
        print(f"round-view: no bed token at {token_path}; run 'bed auth login' first", file=sys.stderr)
        return 2

    sink = _json_sink(args.dump) if args.dump else None
    window = roundview.build_daemon_window(args.url, title=f"Blackjack round: {args.table}",
                                           token=token, table=args.table, sink=sink)
    window.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
