"""WebSocket client that connects an engine to its parent, for an adapter.

The WsClient connects an engine to a gateway on ``ws://host:port/adapter``, where the
gateway reads its profile with ``rois.system.get_profile``. The adapter sends no
registration message. The gateway is the parent engine: it checked the bindings of
every request it forwards, so the adapter serves it through a trusted session.

The lifecycle is:

1. ``engine.start()`` connects the local components to their backends, once.
2. A component that keeps an rclpy node in ``_node`` gets it spun in a background
   thread, when rclpy is installed.
3. The client connects and answers the requests of the gateway, each in its own task,
   until the connection closes. It then reconnects with a growing delay.
4. On cancellation, the rclpy thread stops and ``engine.stop()`` disconnects the
   components.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from functools import partial
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from openrois.engine.engine import Engine
from openrois.engine.jsonrpc import Outbox, send_text, serve_session

logger = logging.getLogger(__name__)

#: The request path the gateway expects child engines on.
ADAPTER_PATH = "/adapter"

# Reconnection backoff, in seconds. A connection that lasted at least
# _STABLE_CONNECTION_SECONDS resets the delay.
_RECONNECT_INITIAL_DELAY = 1.0
_RECONNECT_MAX_DELAY = 30.0
_STABLE_CONNECTION_SECONDS = 10.0


class WsClient:
    """WebSocket client that serves an engine to its parent engine."""

    def __init__(self, engine: Engine, gateway_url: str) -> None:
        """Initialize the WsClient.

        Args:
            engine: The engine, with its components added.
            gateway_url: The WebSocket URL of the gateway. ``/adapter`` is appended
                when the URL does not end with it.
        """
        self._engine = engine
        url = gateway_url.rstrip("/")
        self._url = url if url.endswith(ADAPTER_PATH) else url + ADAPTER_PATH
        self._rclpy_thread: threading.Thread | None = None
        self._rclpy_executor: Any = None

    def run(self) -> None:
        """Serve the gateway until Ctrl+C, reconnecting whenever the connection drops."""
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(self.run_async())

    async def run_async(self) -> None:
        """Serve the gateway until the task is cancelled.

        The coroutine form of :meth:`run`, for callers that already run an event loop,
        such as tests or a process that hosts other tasks.
        """
        loop = asyncio.get_running_loop()
        await self._engine.start()
        self._maybe_start_rclpy()
        delay = _RECONNECT_INITIAL_DELAY
        try:
            while True:
                connection = await self._connect()
                connected_at = loop.time()
                try:
                    await self._serve(connection)
                except Exception:
                    logger.exception("The connection to the gateway failed")
                # A gateway that refuses the adapter, for example for a duplicate
                # engine id, accepts the connection first, so without this pause the
                # adapter would reconnect in a tight loop. The delay grows while
                # connections stay short-lived.
                if loop.time() - connected_at >= _STABLE_CONNECTION_SECONDS:
                    delay = _RECONNECT_INITIAL_DELAY
                logger.info("Reconnecting in %.1fs", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, _RECONNECT_MAX_DELAY)
        finally:
            self._maybe_stop_rclpy()
            await self._engine.stop()
            logger.info("WsClient stopped")

    async def _connect(self) -> ClientConnection:
        """Connect to the gateway, retrying with a growing delay until it answers."""
        delay = _RECONNECT_INITIAL_DELAY
        while True:
            try:
                logger.info("Connecting to %s", self._url)
                return await connect(self._url)
            except (OSError, TimeoutError, InvalidHandshake) as exc:
                logger.warning("Cannot connect to %s: %s. Retrying in %.1fs", self._url, exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, _RECONNECT_MAX_DELAY)

    async def _serve(self, connection: ClientConnection) -> None:
        """Answer the requests of the gateway until the connection closes."""
        logger.info("Connected to the gateway at %s", self._url)
        outbox = Outbox(partial(send_text, connection))
        session = self._engine.open_session(outbox.notify, trusted=True)
        try:
            await serve_session(self._engine, session, outbox, connection)
        finally:
            with contextlib.suppress(ConnectionClosed):
                await connection.close()
            logger.info(
                "Disconnected from the gateway (code %s, reason %r)",
                connection.close_code,
                connection.close_reason,
            )

    # -- rclpy threading -----------------------------------------------------------------

    def _maybe_start_rclpy(self) -> None:
        """Spin the rclpy nodes of the components in a background thread, if any."""
        nodes = [
            node
            for component in self._engine.local_components()
            if (node := getattr(component, "_node", None)) is not None
        ]
        if not nodes:
            return
        try:
            from rclpy.executors import MultiThreadedExecutor
        except ImportError:
            logger.debug("rclpy is not installed, so no ROS 2 node is spun")
            return
        self._rclpy_executor = MultiThreadedExecutor()
        for node in nodes:
            self._rclpy_executor.add_node(node)
        self._rclpy_thread = threading.Thread(
            target=self._rclpy_executor.spin, daemon=True, name="rclpy-spin"
        )
        self._rclpy_thread.start()
        logger.info("Spinning %d rclpy nodes in a background thread", len(nodes))

    def _maybe_stop_rclpy(self) -> None:
        """Stop the rclpy background thread if it was started."""
        if self._rclpy_executor is not None:
            self._rclpy_executor.shutdown()
            self._rclpy_executor = None
        if self._rclpy_thread is not None:
            self._rclpy_thread.join(timeout=5.0)
            self._rclpy_thread = None
