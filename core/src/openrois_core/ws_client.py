"""WebSocket client for OpenRoIS adapters.

The WsClient connects an adapter (Engine with local components) to a
gateway over WebSocket. It handles:

- WebSocket connection to the gateway (ws://host:port/adapter).
- Automatic reconnection with exponential backoff.
- JSON-RPC request/response dispatch to local component handlers.
- Event emission via EventEmitter (thread-safe emit).
- rclpy threading: spins ROS 2 nodes in a background thread if rclpy
  is installed and components have nodes.

The lifecycle is:
1. connect_all() on all local components.
2. Start rclpy executor if any components have nodes.
3. Enter the reconnect loop: connect -> dispatch.
4. On disconnect: stop rclpy -> disconnect_all -> connect_all -> restart rclpy.

The gateway discovers the adapter's components via rois.command.search
when the WebSocket connects. The adapter no longer sends a registration
message.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

import websockets

from openrois_core.engine import Engine, EventEmitter

logger = logging.getLogger(__name__)


class WsClient:
    """WebSocket client that connects an Engine to a gateway.

    The WsClient owns the connection lifecycle: token acquisition,
    reconnection, and event emission. It reads the gateway URL from
    the profile's engine.gateway_url key.
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

        self._ws: Any = None
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
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        """Async main: connect, register, dispatch, reconnect on disconnect."""
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

        try:
            while True:
                try:
                    ws = await self._connect_with_retry()
                    if ws is None:
                        break
                    self._ws = ws
                    logger.info("Connected to gateway at %s", self._gateway_url)

                    await self._dispatch_loop()
                except websockets.ConnectionClosed:
                    logger.info("WebSocket closed, reconnecting...")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Client error: %s", exc)
                finally:
                    if self._ws is not None:
                        try:
                            await self._ws.close()
                        except Exception:
                            pass
                        self._ws = None
                    if self._emitter:
                        self._emitter.remove_all_subscriptions()
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
    ) -> Any | None:
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
                if "/adapter" not in url:
                    url = url.rstrip("/") + "/adapter"
                logger.info("Connecting to %s", url)
                ws = await websockets.connect(url)
                return ws
            except (
                ConnectionRefusedError,
                OSError,
                websockets.ConnectionClosed,
            ) as exc:
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
        """Send a raw JSON string over the WebSocket."""
        if self._ws:
            await self._ws.send(msg)

    async def _dispatch_loop(self) -> None:
        """Receive JSON-RPC requests and dispatch to handler methods."""
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON: %s", raw[:100])
                continue

            if "id" not in msg or "method" not in msg:
                logger.warning("Message without id or method: %s", msg)
                continue

            request_id = msg["id"]
            method = msg["method"]
            params = msg.get("params", {})

            result = await self._dispatch(method, params)
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
            await self._ws.send(json.dumps(response))

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