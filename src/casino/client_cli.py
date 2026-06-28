# casino/client_cli.py
# Console-script entry point for the standalone casino remote client.
#
# Usage:
#     casino-client [--host HOST] [--port PORT]

from __future__ import annotations

import argparse

from .client import CasinoClient


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="casino-client",
        description="Standalone casino remote client (talks to the BED casino server).",
    )
    p.add_argument("--host", default="localhost", help="BED server host (default: localhost)")
    p.add_argument("--port", type=int, default=8765, help="BED server port (default: 8765)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = CasinoClient(args)
    client.run()
    return 0 if client.authenticated else 1


if __name__ == "__main__":
    raise SystemExit(main())
