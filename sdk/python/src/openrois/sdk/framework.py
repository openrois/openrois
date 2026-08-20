"""AdapterFramework: the runtime that connects an adapter to the avatar.

The framework handles:
- WebSocket connection to the avatar (ws://host:port).
- Automatic reconnection with exponential backoff when the WebSocket
  drops. The adapter keeps running and retries indefinitely.
- Component registration on each connect (rois.adapter.register).
- JSON-RPC request/response dispatch to @query/@invoke/@subscribe handlers.
- Event emission via EventEmitter (thread-safe emit()).
- subscribe_id generation and unsubscribe cleanup.
- rclpy threading: spins the ROS 2 node in a background thread if rclpy
  is installed. The rclpy thread persists across reconnections.

The roboticist does not interact with the framework directly. They write
a RobotAdapter subclass and call AdapterFramework.run().

Usage::

    config = load_config("openrois-profile.yaml")
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
            config: The loaded config dict (from openrois-profile.yaml).
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

        This is the main entry point. It blocks until the framework is
        cancelled (KeyboardInterrupt or task cancellation). On WebSocket
        disconnect, it reconnects and re-registers automatically with
        exponential backoff, retrying indefinitely.

        The adapter's ``connect()`` and rclpy background thread are started
        once before the first connection attempt and remain alive across
        reconnections. The adapter's ``disconnect()`` and rclpy shutdown run
        only when the framework exits for good.

        If the adapter has an async ``connect`` method, it is called inside
        the framework's event loop before connecting to the avatar. This
        ensures that gRPC clients and other async resources created in
        ``connect()`` are bound to the same loop as the framework.
        """
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        """Async main: connect, register, dispatch, reconnect on disconnect.

        The outer loop retries the connect-register-dispatch cycle
        indefinitely. When the WebSocket drops (avatar app closed,
        network failure), the framework logs the disconnect, clears
        the stale connection state, and reconnects with backoff. The
        rclpy background thread and adapter ``connect()`` resources
        persist across reconnections.
        """
        self._loop = asyncio.get_running_loop()

        # Set up the EventEmitter and inject emit() into the adapter.
        self._emitter = EventEmitter(self._ws_send, self._loop)
        self.adapter.emit = self._emitter.emit  # type: ignore[attr-defined]

        # Call the adapter's async connect() once, before any WebSocket
        # connection. This runs inside the framework's event loop so that
        # gRPC channels and other async resources bind to the same loop.
        # connect() resources persist across reconnections.
        connect_method = getattr(self.adapter, "connect", None)
        if connect_method is not None and asyncio.iscoroutinefunction(connect_method):
            logger.info("Calling adapter.connect()")
            await connect_method()

        # Start rclpy in a background thread once. The thread persists
        # across reconnections so ROS 2 subscriptions keep firing.
        self._maybe_start_rclpy()

        try:
            while True:
                try:
                    ws = await self._connect_with_retry()
                    if ws is None:
                        break
                    self._ws = ws
                    logger.info("Connected to avatar at %s", self.ws_url)

                    await self._register()
                    await self._dispatch_loop()
                except websockets.ConnectionClosed:
                    logger.info(
                        "WebSocket connection closed, reconnecting..."
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Framework error: %s", exc)
                finally:
                    # Clean up the stale connection state so the next
                    # iteration starts fresh. Do NOT stop rclpy or call
                    # adapter.disconnect() here: those run only on final
                    # exit. Clearing _ws makes _ws_send a no-op during
                    # the reconnection window, preventing sends to a
                    # dead socket.
                    if self._ws is not None:
                        try:
                            await self._ws.close()
                        except Exception:
                            pass
                        self._ws = None
                    if self._emitter:
                        self._emitter.remove_all_subscriptions()
        except asyncio.CancelledError:
            logger.info("Adapter framework cancelled")
        finally:
            self._maybe_stop_rclpy()
            if self._emitter:
                self._emitter.remove_all_subscriptions()
            disconnect_method = getattr(self.adapter, "disconnect", None)
            if disconnect_method is not None and asyncio.iscoroutinefunction(disconnect_method):
                try:
                    await disconnect_method()
                except Exception as exc:
                    logger.warning("Adapter disconnect error: %s", exc)
            logger.info("Adapter framework stopped")

    async def _connect_with_retry(
        self,
        max_retries: int = 0,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> Any | None:
        """Connect to the avatar with exponential backoff retry.

        If max_retries is 0, retry forever. The adapter waits for the
        avatar to start instead of crashing on connection refused.

        Args:
            max_retries: Maximum number of retries (0 = infinite).
            initial_delay: Initial delay between retries in seconds.
            max_delay: Maximum delay between retries in seconds.

        Returns:
            The WebSocket connection, or None if retries exhausted.
        """
        delay = initial_delay
        attempt = 0
        while True:
            try:
                logger.info("Connecting to %s", self.ws_url)
                ws = await websockets.connect(self.ws_url)
                return ws
            except (
                ConnectionRefusedError,
                OSError,
                websockets.ConnectionClosed,
            ) as exc:
                attempt += 1
                if max_retries > 0 and attempt > max_retries:
                    logger.error(
                        "Failed to connect after %d retries: %s",
                        max_retries, exc,
                    )
                    return None
                logger.warning(
                    "Cannot connect to %s: %s. Retrying in %.1fs...",
                    self.ws_url, exc, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)

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
        elif method == "rois.command.bind":
            return self._handle_bind(bare_ref)
        elif method == "rois.command.release":
            return self._handle_release(bare_ref)
        elif method == "rois.event.subscribe":
            return await self._handle_subscribe(bare_ref, params)
        elif method == "rois.event.unsubscribe":
            return await self._handle_unsubscribe(params)
        elif method == "rois.system.connect":
            return {"return_code": ReturnCode.OK.value}
        elif method == "rois.system.disconnect":
            return {"return_code": ReturnCode.OK.value}
        elif method == "rois.system.get_profile":
            return self._handle_get_profile()
        else:
            return {"return_code": ReturnCode.UNSUPPORTED.value}

    def _handle_bind(self, bare_ref: str) -> dict[str, Any]:
        """Handle rois.command.bind.

        Adapters that do not require bind can ignore this call. The
        framework acknowledges bind so the caller can proceed with
        execute. Components with bind_required=True are tracked so
        release can clear the binding.
        """
        meta = self.adapter.get_metadata(bare_ref)
        if not meta:
            return {"return_code": ReturnCode.UNSUPPORTED.value}
        # Acknowledge the bind. No per-operator tracking yet.
        return {"return_code": ReturnCode.OK.value}

    def _handle_release(self, bare_ref: str) -> dict[str, Any]:
        """Handle rois.command.release.

        Clears any binding held by the caller. Acknowledged even if
        no binding existed.
        """
        meta = self.adapter.get_metadata(bare_ref)
        if not meta:
            return {"return_code": ReturnCode.UNSUPPORTED.value}
        return {"return_code": ReturnCode.OK.value}

    def _handle_get_profile(self) -> dict[str, Any]:
        """Build a profile response from registered component metadata.

        Returns a profile wrapper with an identifier, component_ids
        (with the fleet_id prefix), and component_profiles (with query,
        command, and event name lists). The caller (avatar) can match
        components by capability instead of by name. Matches the RoIS
        spec HRI_Engine_Profile shape: the component_ids and
        component_profiles are nested under a "profile" key with an
        identifier.
        """
        component_ids: list[str] = []
        component_profiles: list[dict[str, Any]] = []

        for ref, meta in self.adapter._metadata.items():
            full_ref = f"{self.fleet_id}/{ref}"
            component_ids.append(full_ref)
            component_profiles.append({
                "identifier": {
                    "authority": "OpenRoIS",
                    "code": ref,
                    "codebook_ref": "",
                    "version": "",
                },
                "query_profiles": [
                    {"name": q} for q in meta.queries
                ],
                "command_profiles": [
                    {"name": c} for c in meta.invokes
                ],
                "event_profiles": [
                    {"name": e} for e in meta.subscribes
                ],
            })

        return {
            "return_code": ReturnCode.OK.value,
            "profile": {
                "identifier": {
                    "authority": "OpenRoIS",
                    "code": self.fleet_id or "AdapterFramework",
                    "codebook_ref": "",
                    "version": "",
                },
                "component_ids": component_ids,
                "component_profiles": component_profiles,
            },
        }

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

        # Support both the spec structured format (command_unit_list)
        # and the legacy flat format (command_type + parameters). The
        # command_type values are lowercase per the RoIS spec
        # (start, stop, suspend, resume, set_parameter, execute).
        command_unit_list = params.get("command_unit_list", [])
        if isinstance(command_unit_list, list) and len(command_unit_list) > 0:
            unit = command_unit_list[0]
            command_type = str(unit.get("command_type", "execute"))
            raw_params = unit.get("arguments", [])
        else:
            command_type = str(params.get("command_type", "execute"))
            raw_params = params.get("parameters", params.get("arguments", []))
        method_name = meta.invokes.get(command_type)
        if not method_name:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "command_id": ""}

        method = getattr(handler, method_name)
        # Parse parameters from the request.
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
