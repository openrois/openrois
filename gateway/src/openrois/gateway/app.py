"""The gateway process: one Engine behind one WsServer, with signal handling."""

from __future__ import annotations

import asyncio
import logging
import signal

from openrois.engine import Engine, WsServer

from openrois.gateway.config import GatewayConfig

logger = logging.getLogger(__name__)

#: The signals that stop the gateway gracefully.
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)


class Gateway:
    """The main HRI Engine of an OpenRoIS deployment, on a WebSocket port.

    Adapters and lower gateways connect as child engines on ``/adapter``, and
    service applications connect as clients on any other path. The engine
    enforces bindings, as the Main HRI Engine holds them for the hierarchy.
    """

    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self.engine = Engine(engine_id=config.engine_id, enforce_bindings=True)
        self.server = WsServer(self.engine, child_timeout=config.child_timeout)

    @property
    def port(self) -> int:
        """The bound port, also when the config asked for port 0."""
        return self.server.port

    async def start(self) -> None:
        """Start listening. Returns once the gateway accepts connections."""
        await self.server.start(self.config.host, self.config.port)

    async def stop(self) -> None:
        """Close every connection and stop listening."""
        await self.server.stop()

    async def run(self, stop: asyncio.Event | None = None) -> None:
        """Serve until SIGTERM or SIGINT arrives, or until ``stop`` is set.

        Args:
            stop: An event that stops the gateway when set, for callers that
                run it inside a larger program. The signals stop it as well.
        """
        stop = stop or asyncio.Event()
        await self.start()

        loop = asyncio.get_running_loop()
        installed = []
        for sig in STOP_SIGNALS:
            try:
                loop.add_signal_handler(sig, stop.set)
                installed.append(sig)
            except (NotImplementedError, RuntimeError):
                # Windows event loops and non-main threads cannot install
                # signal handlers. There, Ctrl+C raises KeyboardInterrupt,
                # which the command-line entry point handles.
                pass

        try:
            await stop.wait()
            logger.info("Stopping")
        finally:
            for sig in installed:
                loop.remove_signal_handler(sig)
            await self.stop()
            logger.info("Stopped")
