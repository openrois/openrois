"""WebSocket client for OpenRoIS adapters.

The WsClient connects an adapter (Engine with local components) to a
gateway over WebSocket. It handles:

- WebSocket connection to the gateway (ws://host:port/adapter).
- Automatic reconnection with exponential backoff.
- JSON-RPC request/response dispatch to local component handlers, each
  request in its own task so a slow command does not block the others.
- Event emission via EventEmitter (thread-safe emit).
- rclpy threading: spins ROS 2 nodes in a background thread if rclpy
  is installed and components have nodes.

The lifecycle is:
1. connect_all() on all local components.
2. Start rclpy executor if any components have nodes.
3. Enter the reconnect loop: connect -> dispatch.
4. On cancellation: stop rclpy -> disconnect_all.

The gateway discovers the adapter's components via rois.command.search
when the WebSocket connects. The adapter sends no registration message.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from openrois.engine.engine import Engine, EventEmitter

logger = logging.getLogger(__name__)

#: The request path the gateway expects child engines on.
ADAPTER_PATH = "/adapter"

# Reconnection backoff, in seconds. A connection that lasted at least
# _STABLE_CONNECTION_SECONDS resets the delay.
_RECONNECT_INITIAL_DELAY = 1.0
_RECONNECT_MAX_DELAY = 30.0
_STABLE_CONNECTION_SECONDS = 10.0


class WsClient:
    """WebSocket client that connects an Engine to a gateway.

    The WsClient owns the connection lifecycle: connection, reconnection,
    request dispatch and event emission.
    """

    def __init__(
        self,
        engine: Engine,
        gateway_url: str,
    ) -> None:
        """Initialize the WsClient.

        Args:
            engine: The Engine instance with local components registered.
            gateway_url: The WebSocket URL of the gateway.
        """
        self._engine = engine
        self._gateway_url = gateway_url

        self._ws: ClientConnection | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._emitter: EventEmitter | None = None
        self._rclpy_thread: threading.Thread | None = None
        self._rclpy_executor: Any = None

    def run(self) -> None:
        """Connect to the gateway, register, and dispatch until cancelled.

        This is the main entry point. It blocks until cancelled
        (KeyboardInterrupt or task cancellation). On WebSocket disconnect,
        it reconnects and re-registers automatically with exponential
        backoff, retrying indefinitely.
        """
        asyncio.run(self.run_async())

    async def run_async(self) -> None:
        """Connect, dispatch and reconnect until the task is cancelled.

        The coroutine form of :meth:`run`, for callers that already run an
        event loop, such as tests or a process that hosts other tasks.
        """
        self._loop = asyncio.get_running_loop()

        # Set up the EventEmitter with the initial send function.
        self._emitter = EventEmitter(self._ws_send, self._loop)

        # Inject emitter onto the component registry.
        self._engine.component_registry.set_emitter(self._emitter)

        # Call connect_all() once before the first connection.
        registry = self._engine.component_registry
        await registry.connect_all()

        # Start rclpy in a background thread if any components have nodes.
        self._maybe_start_rclpy()

        delay = _RECONNECT_INITIAL_DELAY
        try:
            while True:
                connected_at: float | None = None
                try:
                    ws = await self._connect_with_retry()
                    if ws is None:
                        break
                    self._ws = ws
                    connected_at = self._loop.time()
                    logger.info("Connected to gateway at %s", self._gateway_url)

                    await self._dispatch_loop()
                except ConnectionClosed:
                    pass
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Client error: %s", exc)
                finally:
                    ws = self._ws
                    self._ws = None
                    if ws is not None:
                        await ws.close()
                        logger.info(
                            "Disconnected from the gateway (code %s, reason %r).",
                            ws.close_code,
                            ws.close_reason,
                        )
                    if self._emitter:
                        self._emitter.remove_all_subscriptions()

                # Wait before reconnecting. A gateway that refuses the adapter,
                # for example for a duplicate engine id, accepts the connection
                # first, so without this pause the adapter would reconnect in a
                # tight loop. The delay grows while connections stay short-lived.
                stable = (
                    connected_at is not None
                    and self._loop.time() - connected_at >= _STABLE_CONNECTION_SECONDS
                )
                delay = _RECONNECT_INITIAL_DELAY if stable else delay
                logger.info("Reconnecting in %.1fs...", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, _RECONNECT_MAX_DELAY)
        except asyncio.CancelledError:
            logger.info("WsClient cancelled")
        finally:
            self._maybe_stop_rclpy()
            if self._emitter:
                self._emitter.remove_all_subscriptions()
            await registry.disconnect_all()
            logger.info("WsClient stopped")

    async def _connect_with_retry(
        self,
        max_retries: int = 0,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> ClientConnection | None:
        """Connect to the gateway with exponential backoff retry.

        Args:
            max_retries: Maximum retries (0 = infinite).
            initial_delay: Initial delay in seconds.
            max_delay: Maximum delay in seconds.

        Returns:
            The WebSocket connection, or None if retries exhausted.
        """
        delay = initial_delay
        attempt = 0
        while True:
            try:
                url = self._gateway_url
                if not url.rstrip("/").endswith(ADAPTER_PATH):
                    url = url.rstrip("/") + ADAPTER_PATH
                logger.info("Connecting to %s", url)
                return await connect(url)
            except (OSError, TimeoutError, InvalidHandshake) as exc:
                attempt += 1
                if max_retries > 0 and attempt > max_retries:
                    logger.error("Failed after %d retries: %s", max_retries, exc)
                    return None
                logger.warning(
                    "Cannot connect to %s: %s. Retrying in %.1fs...",
                    self._gateway_url, exc, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)

    async def _ws_send(self, msg: str) -> None:
        """Send a raw JSON string over the WebSocket, if one is open.

        Events emitted while the adapter is between connections are dropped:
        the gateway has forgotten the subscriptions they belong to.
        """
        ws = self._ws
        if ws is None:
            return
        try:
            await ws.send(msg)
        except ConnectionClosed:
            logger.debug("Dropped a message for a closed connection.")

    async def _dispatch_loop(self) -> None:
        """Receive JSON-RPC requests and answer each in its own task."""
        ws = self._ws
        if ws is None:
            return
        tasks: set[asyncio.Task[None]] = set()
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    logger.warning("Invalid JSON from the gateway.")
                    continue

                if not isinstance(msg, dict) or "id" not in msg or "method" not in msg:
                    logger.warning("Message without id or method: %s", msg)
                    continue

                task = asyncio.create_task(self._answer(ws, msg))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _answer(self, ws: ClientConnection, msg: dict[str, Any]) -> None:
        """Dispatch one request from the gateway and send the reply."""
        params = msg.get("params", {})
        if not isinstance(params, dict):
            params = {}
        result = await self._dispatch(str(msg["method"]), params)
        response = {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": result,
        }
        try:
            await ws.send(json.dumps(response))
        except ConnectionClosed:
            logger.debug("Dropped a reply for a closed connection.")

    async def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route a JSON-RPC method to the engine's dispatch."""
        return await self._engine.dispatch(method, params)

    # -- rclpy threading --

    def _maybe_start_rclpy(self) -> None:
        """Start rclpy in a background thread if any components have nodes."""
        nodes = self._engine.component_registry.get_rclpy_nodes()
        if not nodes:
            return

        try:
            import rclpy  # noqa: F401
            from rclpy.executors import MultiThreadedExecutor
        except ImportError:
            logger.debug("rclpy not installed, skipping ROS 2 spin")
            return

        self._rclpy_executor = MultiThreadedExecutor()
        for node in nodes:
            self._rclpy_executor.add_node(node)
        self._rclpy_thread = threading.Thread(
            target=self._rclpy_executor.spin,
            daemon=True,
            name="rclpy-spin",
        )
        self._rclpy_thread.start()
        logger.info("Started rclpy spin in background thread")

    def _maybe_stop_rclpy(self) -> None:
        """Stop the rclpy background thread if it was started."""
        if self._rclpy_executor:
            self._rclpy_executor.shutdown()
            self._rclpy_executor = None
        if self._rclpy_thread:
            self._rclpy_thread.join(timeout=5.0)
            self._rclpy_thread = None
