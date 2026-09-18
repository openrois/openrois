"""The OpenRoIS gateway process.

Composes an Engine (the main HRI Engine, enforcing reservations) with a
WsServer, and serves until interrupted. Run it with ``openrois-gateway`` or
``python -m openrois_core.gateway``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from collections.abc import Sequence

from openrois_core.engine import Engine
from openrois_core.ws_server import WsServer

logger = logging.getLogger("openrois.gateway")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openrois-gateway",
        description="Run an OpenRoIS gateway (main HRI Engine) on a WebSocket port.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="interface to bind (default: all)")
    parser.add_argument("--port", type=int, default=8765, help="port to listen on (default: 8765)")
    parser.add_argument("--engine-id", default="gateway", help="engine identifier in the profile")
    parser.add_argument("--platform", default="", help="platform identifier in the profile")
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser


async def serve(
    host: str,
    port: int,
    engine_id: str = "gateway",
    platform: str = "",
    stop: asyncio.Event | None = None,
) -> None:
    """Serve until ``stop`` is set (or forever), then shut the server down cleanly."""
    engine = Engine(engine_id=engine_id, platform=platform, enforce_bindings=True)
    server = WsServer(engine)
    await server.start(host, port)
    stop = stop or asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            # Signal handlers are unavailable on some platforms and in threads.
            pass
    try:
        await stop.wait()
    finally:
        logger.info("Gateway shutting down")
        await server.stop()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(serve(args.host, args.port, args.engine_id, args.platform))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
