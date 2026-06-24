#!/usr/bin/env python3
# casino/bed.py
# BED - BBS Engine Daemon
# WebSocket server for casino system using bbsengine6.net service registry

import argparse
import asyncio
import signal
import sys

from bbsengine6 import io
from bbsengine6.net import WebSocketServer
from bbsengine6.util import getcurrentloginid
from bbsengine6.database import buildargs as databasebuildargs
from casino.api.handler import MessageRouter
from casino import config


class BED:
    """BBS Engine Daemon - WebSocket server with service registry."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.server: WebSocketServer | None = None
        self.router: MessageRouter | None = None
        self._running = False

    async def start(self) -> None:
        """Start the daemon."""
        # Create WebSocket server
        self.server = WebSocketServer(
            host=self.args.host,
            port=self.args.port,
        )

        # Create message router and register services
        # Set up database args for bbsengine6
        db_args = argparse.Namespace()
        db_args.databasename = self.args.databasename
        db_args.databasehost = self.args.databasehost
        db_args.databaseport = self.args.databaseport
        db_args.databaseuser = self.args.databaseuser
        db_args.databasepassword = self.args.databasepassword
        db_args.debug = self.args.debug

        # Initialize database pool
        from bbsengine6 import database
        try:
            db_args.pool = database.getpool(db_args)
            # Test the pool with a quick connection check
            with db_args.pool.connection() as conn:
                pass
        except Exception as e:
            io.echo(f"Database connection failed: {e}", level="error")
            io.echo("Please ensure PostgreSQL is running with correct credentials", level="error")
            return

        self.router = MessageRouter(db_args)
        self.router.register_all(self.server)

        # Start server
        await self.server.start()
        self._running = True

        io.echo(f"BED started on {self.args.host}:{self.args.port}", level="info")
        io.echo(f"Registered services: {self.server.list_services()}", level="info")

        # Keep running
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            io.echo("BED cancelled", level="info")

    async def stop(self) -> None:
        """Stop the daemon."""
        self._running = False
        if self.server:
            await self.server.stop()
        io.echo("BED stopped", level="info")

    async def restart(self) -> None:
        """Restart the daemon."""
        await self.stop()
        await self.start()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BED - BBS Engine Daemon")
    databasebuildargs(parser)
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to listen on (default: 8765)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--foreground", "-f",
        action="store_true",
        help="Run in foreground (don't daemonize)",
    )
    parser.add_argument(
        "--pidfile",
        help="Path to PID file",
    )
    parser.add_argument(
        "--autorestart",
        action="store_true",
        default=None,
        help="Enable auto-restart on crash (default: from bed.json, or True)",
    )
    parser.add_argument(
        "--no-autorestart",
        action="store_true",
        default=False,
        help="Disable auto-restart on crash",
    )
    parser.add_argument(
        "--restart-delay",
        type=int,
        default=None,
        help="Seconds to wait before restarting (default: from bed.json, or 5)",
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=None,
        help="Max consecutive restarts before giving up (default: from bed.json, or 10)",
    )
    return parser.parse_args()


def get_autorestart_config(args: argparse.Namespace) -> tuple[bool, int, int]:
    """Get autorestart config from args or bed.json defaults."""
    bed_config = config.load_config().get("bed", {})

    # Determine autorestart enabled
    if args.no_autorestart:
        autorestart = False
    elif args.autorestart is not None:
        autorestart = args.autorestart
    else:
        autorestart = bed_config.get("autorestart", True)

    # Determine restart delay
    restart_delay = args.restart_delay if args.restart_delay is not None else bed_config.get("restart_delay", 5)

    # Determine max restarts
    max_restarts = args.max_restarts if args.max_restarts is not None else bed_config.get("max_restarts", 10)

    return autorestart, restart_delay, max_restarts


async def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Get autorestart config
    autorestart, restart_delay, max_restarts = get_autorestart_config(args)

    # Track restart count for autorestart
    restart_count = 0

    # Set up signal handlers
    loop = asyncio.get_event_loop()

    # Store bed instance for signal handlers
    bed = None
    config_reloaded = False

    def signal_handler():
        io.echo("Received shutdown signal", level="info")
        if bed:
            asyncio.create_task(bed.stop())

    def sighup_handler():
        nonlocal config_reloaded
        io.echo("Received SIGHUP, reloading config", level="info")
        new_config = config.reload_config()
        io.echo(f"Config reloaded: {new_config}", level="info")
        config_reloaded = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    try:
        loop.add_signal_handler(signal.SIGHUP, sighup_handler)
    except (NotImplementedError, OSError):
        pass

    while True:
        bed = BED(args)

        try:
            await bed.start()
            # If we get here without exception, reset restart count on successful start
            restart_count = 0

            # If we reached here via SIGHUP handler waiting in the main loop,
            # the main loop would have been broken - but we don't exit on SIGHUP
            # The loop continues running

        except Exception as e:
            io.echo_traceback(f"BED error: {e}")

            if autorestart:
                restart_count += 1
                if restart_count > max_restarts:
                    io.echo(f"Max restarts ({max_restarts}) reached, giving up", level="error")
                    await bed.stop()
                    break

                io.echo(f"Auto-restarting in {restart_delay}s (attempt {restart_count}/{max_restarts})", level="warning")
                await bed.stop()
                await asyncio.sleep(restart_delay)
                continue
            else:
                await bed.stop()
                raise

        # If autorestart is disabled and we exit start(), break the loop
        if not autorestart:
            break


if __name__ == "__main__":
    asyncio.run(main())
