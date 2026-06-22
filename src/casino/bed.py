#!/usr/bin/env python3
# casino/bed.py
# BED - BBS Engine Daemon
# WebSocket server for casino system using bbsengine6.net service registry

import argparse
import asyncio
import logging
import signal
import sys

# Add src to path for imports
sys.path.insert(0, "/home/opencode/data/work/casino/src")

from bbsengine6.net import WebSocketServer
from bbsengine6.util import getcurrentloginid
from bbsengine6.database import buildargs as databasebuildargs
from casino.api.handler import MessageRouter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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
            logger.error(f"Database connection failed: {e}")
            logger.error("Please ensure PostgreSQL is running with correct credentials")
            return

        self.router = MessageRouter(db_args)
        self.router.register_all(self.server)

        # Start server
        await self.server.start()
        self._running = True

        logger.info(f"BED started on {self.args.host}:{self.args.port}")
        logger.info(f"Registered services: {self.server.list_services()}")

        # Keep running
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("BED cancelled")

    async def stop(self) -> None:
        """Stop the daemon."""
        self._running = False
        if self.server:
            await self.server.stop()
        logger.info("BED stopped")

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
    return parser.parse_args()


async def main() -> None:
    """Main entry point."""
    args = parse_args()

    bed = BED(args)

    # Set up signal handlers
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(bed.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await bed.start()
    except Exception as e:
        logger.error(f"BED error: {e}")
        await bed.stop()
        raise


if __name__ == "__main__":
    asyncio.run(main())
