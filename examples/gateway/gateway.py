"""Minimal OpenRoIS gateway process (Python).

Composes the recursive Engine and WsServer from openrois_core into a
single gateway process. This is the Python counterpart of the
TypeScript gateway in `gateway/` (roadmap Phase 6: "Gateway Process").

The gateway has no local components. Adapters connect on the
/adapter path and are discovered via rois.command.search. Clients
connect on any other path and send RoIS operations.

Usage:
    python gateway.py [--host HOST] [--port PORT]

Environment overrides: ENGINE_HOST, ENGINE_PORT.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from openrois_core import Engine, WsServer

logger = logging.getLogger(__name__)


async def main(host: str, port: int) -> None:
    # Gateway mode: enforce bind/release on execute. Only the client
    # that called bind() can execute() on actuation components.
    engine = Engine(enforce_bindings=True)
    ws_server = WsServer(engine)

    await ws_server.start(host, port)
    logger.info("OpenRoIS Gateway ready on ws://%s:%d", host, port)
    print(f"OpenRoIS Gateway ready on ws://{host}:{port}")

    # Run until cancelled.
    try:
        await asyncio.get_running_loop().create_future()
    finally:
        await ws_server.stop()
        logger.info("Gateway stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="OpenRoIS gateway (Python)")
    parser.add_argument(
        "--host",
        default=os.environ.get("ENGINE_HOST", "0.0.0.0"),
        help="Host to bind (default: 0.0.0.0, or ENGINE_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ENGINE_PORT", "8765")),
        help="Port to listen on (default: 8765, or ENGINE_PORT)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.host, args.port))
    except KeyboardInterrupt:
        print("Gateway interrupted")