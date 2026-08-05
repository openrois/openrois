"""AdapterFramework: the runtime that connects an adapter to the avatar.

The framework handles:
- WebSocket connection to the avatar (ws://host:port).
- Component registration on connect (rois.adapter.register).
- JSON-RPC request/response dispatch to @query/@invoke/@subscribe handlers.
- Event emission via EventEmitter (thread-safe emit()).
- subscribe_id generation and unsubscribe cleanup.
- rclpy threading: spins the ROS 2 node in a background thread if rclpy
  is installed.

The roboticist does not interact with the framework directly. They write
a RobotAdapter subclass and call AdapterFramework.run().

Usage::

    config = load_config("profile.yaml")
    adapter = MyAdapter(config)
    framework = AdapterFramework(adapter, config)
    framework.run()
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

import websockets
from openrois.interfaces.hri import ReturnCode

from openrois.sdk.adapter import RobotAdapter
from openrois.sdk.events import EventEmitter

logger = logging.getLogger(__name__)


class AdapterFramework:
    """Runtime that connects a RobotAdapter to the avatar via WebSocket.

    The framework:
    1. Connects to ws://host:port from the config.
    2. Sends rois.adapter.register with the component list.
    3. Receives JSON-RPC requests and dispatches to handler methods.
    4. Sends JSON-RPC responses back.
    5. Manages event subscriptions and emission.

    Attributes:
        adapter: The RobotAdapter instance.
        ws_url: The WebSocket URL to connect to.
        fleet_id: The fleet ID from the config.
    """

    def __init__(
        self,
        adapter: RobotAdapter,
        config: dict[str, Any],
    ) -> None:
        """Initialize the framework.

        Args:
            adapter: The RobotAdapter instance with @component handlers.
            config: The loaded config dict (from profile.yaml).
        """
        self.adapter = adapter
        self._config = config

        connection = config.get("connection", {})
        ws_config = connection.get("ws", {})
        host = ws_config.get("host", "127.0.0.1")
        port = ws_config.get("port", 8765)
        self.ws_url = f"ws://{host}:{port}"
        self.fleet_id = str(config.get("fleet_id", "robot_1"))

        self._ws: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._emitter: EventEmitter | None = None
        self._rclpy_thread: threading.Thread | None = None
        self._rclpy_executor: Any = None

    def run(self) -> None:
        """Connect to the avatar, register, and dispatch until disconnected.

        This is the main entry point. It blocks until the WS connection
        closes. If rclpy is installed and the adapter has a .node attribute,
        the ROS 2 node is spun in a background thread.
        """
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        """Async main: connect, register, dispatch."""
        self._loop = asyncio.get_running_loop()

        # Set up the EventEmitter and inject emit() into the adapter.
        self._emitter = EventEmitter(self._ws_send, self._loop)
        self.adapter.emit = self._emitter.emit  # type: ignore[attr-defined]

        # Start rclpy in a background thread if available.
        self._maybe_start_rclpy()

        try:
            logger.info("Connecting to %s", self.ws_url)
            async with websockets.connect(self.ws_url) as ws:
                self._ws = ws
                logger.info("Connected to avatar at %s", self.ws_url)

                # Register components.
                await self._register()

                # Dispatch loop.
                await self._dispatch_loop()
        except websockets.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as exc:
            logger.error("Framework error: %s", exc)
            raise
        finally:
            self._maybe_stop_rclpy()
            if self._emitter:
                self._emitter.remove_all_subscriptions()
            logger.info("Adapter framework stopped")

    async def _ws_send(self, msg: str) -> None:
        """Send a raw JSON string over the WebSocket."""
        if self._ws:
            await self._ws.send(msg)

    async def _register(self) -> None:
        """Send rois.adapter.register with the component list."""
        components = self.adapter.get_component_list()
        msg = {
            "jsonrpc": "2.0",
            "id": "reg-1",
            "method": "rois.adapter.register",
            "params": {
                "fleet_id": self.fleet_id,
                "components": components,
            },
        }
        await self._ws.send(json.dumps(msg))
        logger.info(
            "Registered fleet %s with %d components",
            self.fleet_id,
            len(components),
        )

        # Wait for the registration response.
        raw = await self._ws.recv()
        response = json.loads(raw)
        if response.get("result", {}).get("return_code") != ReturnCode.OK.value:
            logger.error("Registration failed: %s", response)
            raise RuntimeError("Adapter registration rejected by avatar")
        logger.info("Registration accepted")

    async def _dispatch_loop(self) -> None:
        """Receive JSON-RPC requests and dispatch to handler methods."""
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON received: %s", raw[:100])
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
        """Route a JSON-RPC method to the right adapter handler.

        Args:
            method: The JSON-RPC method name.
            params: The method parameters.

        Returns:
            The result dict for the JSON-RPC response.
        """
        # Strip fleet_id prefix from component_ref if present.
        component_ref = str(params.get("component_ref", ""))
        bare_ref = component_ref.split("/", 1)[1] if "/" in component_ref else component_ref

        if method == "rois.query.query":
            return await self._handle_query(bare_ref, params)
        elif method == "rois.command.execute":
            return await self._handle_invoke(bare_ref, params)
        elif method == "rois.event.subscribe":
            return await self._handle_subscribe(bare_ref, params)
        elif method == "rois.event.unsubscribe":
            return await self._handle_unsubscribe(params)
        elif method == "rois.system.connect":
            return {"return_code": ReturnCode.OK.value}
        elif method == "rois.system.disconnect":
            return {"return_code": ReturnCode.OK.value}
        else:
            return {"return_code": ReturnCode.UNSUPPORTED.value}

    async def _handle_query(
        self,
        bare_ref: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a rois.query.query request to a @query handler."""
        handler = self.adapter.get_handler(bare_ref)
        if not handler:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "results": []}

        meta = self.adapter.get_metadata(bare_ref)
        if not meta:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "results": []}

        query_type = str(params.get("query_type", ""))
        method_name = meta.queries.get(query_type)
        if not method_name:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "results": []}

        method = getattr(handler, method_name)
        try:
            result_list = await method()
            return {
                "return_code": ReturnCode.OK.value,
                "results": [r.model_dump() for r in result_list],
            }
        except Exception as exc:
            logger.error("Query handler error for %s/%s: %s", bare_ref, query_type, exc)
            return {"return_code": ReturnCode.ERROR.value, "results": []}

    async def _handle_invoke(
        self,
        bare_ref: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a rois.command.execute request to an @invoke handler."""
        handler = self.adapter.get_handler(bare_ref)
        if not handler:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "command_id": ""}

        meta = self.adapter.get_metadata(bare_ref)
        if not meta:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "command_id": ""}

        command_type = str(params.get("command_type", "EXECUTE"))
        method_name = meta.invokes.get(command_type)
        if not method_name:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "command_id": ""}

        method = getattr(handler, method_name)
        # Parse parameters from the request.
        raw_params = params.get("parameters", [])
        parameters = self._parse_parameters(raw_params)

        try:
            response = await method(parameters)
            return {
                "return_code": response.return_code.value,
                "command_id": response.command_id,
            }
        except Exception as exc:
            logger.error("Invoke handler error for %s/%s: %s", bare_ref, command_type, exc)
            return {"return_code": ReturnCode.ERROR.value, "command_id": ""}

    async def _handle_subscribe(
        self,
        bare_ref: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a rois.event.subscribe request to a @subscribe handler."""
        if not self._emitter:
            return {"return_code": ReturnCode.ERROR.value, "subscribe_id": ""}

        handler = self.adapter.get_handler(bare_ref)
        if not handler:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "subscribe_id": ""}

        meta = self.adapter.get_metadata(bare_ref)
        if not meta:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "subscribe_id": ""}

        event_type = str(params.get("event_type", ""))
        method_name = meta.subscribes.get(event_type)
        if not method_name:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "subscribe_id": ""}

        # Register the subscription in the emitter.
        subscribe_id = self._emitter.add_subscription(bare_ref, event_type)

        # Call the handler for setup (e.g., start a poller).
        method = getattr(handler, method_name)
        try:
            await method()
        except Exception as exc:
            logger.error("Subscribe handler error for %s/%s: %s", bare_ref, event_type, exc)
            self._emitter.remove_subscription(subscribe_id)
            return {"return_code": ReturnCode.ERROR.value, "subscribe_id": ""}

        return {
            "return_code": ReturnCode.OK.value,
            "subscribe_id": subscribe_id,
        }

    async def _handle_unsubscribe(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle rois.event.unsubscribe by removing the subscription."""
        if not self._emitter:
            return {"return_code": ReturnCode.ERROR.value}

        subscribe_id = str(params.get("subscribe_id", ""))
        self._emitter.remove_subscription(subscribe_id)
        return {"return_code": ReturnCode.OK.value}

    def _parse_parameters(self, raw: Any) -> list[Any]:
        """Parse the parameters list from a JSON-RPC request.

        Each parameter is a dict with name, data_type_ref, value.
        Returns the list as-is for the handler to interpret.
        """
        if not isinstance(raw, list):
            return []
        return raw

    # ─── rclpy threading ─────────────────────────────────────────

    def _maybe_start_rclpy(self) -> None:
        """Start rclpy in a background thread if the adapter has a .node."""
        node = getattr(self.adapter, "node", None)
        if node is None:
            return

        try:
            import rclpy  # noqa: F401, I001  # type: ignore[import-not-found]
            from rclpy.executors import MultiThreadedExecutor
        except ImportError:
            logger.debug("rclpy not installed, skipping ROS 2 spin")
            return

        self._rclpy_executor = MultiThreadedExecutor()
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
