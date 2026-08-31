"""Recursive Engine, ComponentRegistry, SubEngine, and EventEmitter.

The Engine class is the recursive HRI engine. One class serves both the
gateway (main engine, child engines populated via SubEngine proxies) and
the adapter (local components populated via ComponentRegistry). Both
registries can be populated simultaneously.

ComponentRegistry manages local component handlers. SubEngine is a proxy
for a remote child engine connected via WebSocket. Both implement the
ComponentContract protocol (discover, invoke, query, subscribe,
unsubscribe).

EventEmitter manages event subscriptions and provides thread-safe emit
for pushing event notifications to subscribed clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from openrois.interfaces.hri import Result, ReturnCode

if TYPE_CHECKING:
    from openrois_components_core.meta import ComponentMeta


# ---------------------------------------------------------------------------
# Binding enforcement helper
# ---------------------------------------------------------------------------

_COMMAND_TYPES_REQUIRING_BIND = frozenset({"start", "stop", "suspend", "resume", "execute"})


def _requires_bind(function: str | None, commands: list[str]) -> bool:
    """Derive binding requirement from function classification and commands.

    Actuation components with command methods (start, stop, suspend,
    resume, execute) require exclusive binding. Sensing, streaming, and
    unclassified components do not. set_parameter is excluded: it is
    pre-execute setup per RoIS spec section 7.3.
    """
    if function != "actuation":
        return False
    return bool({c.lower() for c in commands} & _COMMAND_TYPES_REQUIRING_BIND)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EventEmitter
# ---------------------------------------------------------------------------


class EventEmitter:
    """Manages event subscriptions and thread-safe event emission.

    The framework creates one EventEmitter and injects emit/emit_async onto
    each component at registration time. Components call
    self.parent.emit_async(event_type, results) to push events to all
    subscribed operators.

    If nobody is subscribed to an event type, emit is a no-op.
    """

    def __init__(
        self,
        ws_send: Callable[[str], Awaitable[None]],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Initialize the EventEmitter.

        Args:
            ws_send: Async callable that sends a raw JSON string over the WS.
            loop: The asyncio event loop (for thread-safe emit from rclpy).
        """
        self._ws_send = ws_send
        self._loop = loop
        # subscribe_id -> (component_ref, event_type)
        self._subscriptions: dict[str, tuple[str, str]] = {}

    def set_send_fn(self, send_fn: Callable[[str], Awaitable[None]]) -> None:
        """Rebind the send function after reconnect."""
        self._ws_send = send_fn

    def add_subscription(self, component_ref: str, event_type: str) -> str:
        """Register a new subscription and return the subscribe_id."""
        subscribe_id = f"sub-{uuid.uuid4().hex[:8]}"
        self._subscriptions[subscribe_id] = (component_ref, event_type)
        logger.debug(
            "Subscribed %s for %s/%s (%d total)",
            subscribe_id,
            component_ref,
            event_type,
            len(self._subscriptions),
        )
        return subscribe_id

    def remove_subscription(self, subscribe_id: str) -> bool:
        """Remove a subscription by subscribe_id."""
        removed = self._subscriptions.pop(subscribe_id, None)
        if removed:
            logger.debug(
                "Unsubscribed %s (%d remaining)",
                subscribe_id,
                len(self._subscriptions),
            )
        return removed is not None

    def remove_all_subscriptions(self) -> None:
        """Remove all subscriptions. Called on WS disconnect."""
        self._subscriptions.clear()

    def has_subscribers(self, component_ref: str, event_type: str) -> bool:
        """Check if there are active subscribers for a component/event pair."""
        return any(
            (cref, etype) == (component_ref, event_type)
            for cref, etype in self._subscriptions.values()
        )

    def emit(
        self,
        component_ref: str,
        event_type: str,
        results: list[Result],
    ) -> None:
        """Emit an event to all subscribed operators.

        Thread-safe: can be called from a rclpy callback in a background
        thread. Uses asyncio.run_coroutine_threadsafe() to schedule the
        WS send on the main asyncio loop.

        If nobody is subscribed, this is a no-op.
        """
        matching = [
            sid
            for sid, (cref, etype) in self._subscriptions.items()
            if cref == component_ref and etype == event_type
        ]
        if not matching:
            return

        for subscribe_id in matching:
            notification = {
                "jsonrpc": "2.0",
                "method": "rois.event.notify",
                "params": {
                    "event_id": str(uuid.uuid4()),
                    "subscribe_id": subscribe_id,
                    "component_ref": component_ref,
                    "event_type": event_type,
                    "expire": "",
                    "results": [r.model_dump() for r in results],
                },
            }
            msg = json.dumps(notification)
            asyncio.run_coroutine_threadsafe(
                self._ws_send(msg),
                self._loop,
            )

    def emit_async(
        self,
        component_ref: str,
        event_type: str,
        results: list[Result],
    ) -> Awaitable[None]:
        """Async version of emit for use within the asyncio loop."""
        matching = [
            sid
            for sid, (cref, etype) in self._subscriptions.items()
            if cref == component_ref and etype == event_type
        ]
        if not matching:
            return _noop()

        async def _send_all() -> None:
            for subscribe_id in matching:
                notification = {
                    "jsonrpc": "2.0",
                    "method": "rois.event.notify",
                    "params": {
                        "event_id": str(uuid.uuid4()),
                        "subscribe_id": subscribe_id,
                        "component_ref": component_ref,
                        "event_type": event_type,
                        "expire": "",
                        "results": [r.model_dump() for r in results],
                    },
                }
                msg = json.dumps(notification)
                await self._ws_send(msg)

        return _send_all()


async def _noop() -> None:
    """No-op coroutine for emit_async when there are no subscribers."""
    pass


# ---------------------------------------------------------------------------
# ComponentRegistry
# ---------------------------------------------------------------------------


class ComponentRegistry:
    """Manages local component handlers.

    Implements the ComponentContract protocol (discover, invoke, query,
    subscribe, unsubscribe) for in-process components. Each component is
    registered with a ref, a handler instance, and a ComponentMeta.

    The registry injects emit/emit_async onto each component at registration
    time and sets parent to itself so components can call
    self.parent.emit_async(...).
    """

    def __init__(self, emitter: EventEmitter | None = None) -> None:
        self._handlers: dict[str, Any] = {}
        self._metadata: dict[str, ComponentMeta] = {}
        self._emitter = emitter

    @property
    def emit(self) -> Callable[..., None]:
        """Synchronous emit, delegates to EventEmitter."""
        if self._emitter:
            return self._emitter.emit
        raise RuntimeError("No emitter set")

    @property
    def emit_async(self) -> Callable[..., Awaitable[None]]:
        """Async emit, delegates to EventEmitter."""
        if self._emitter:
            return self._emitter.emit_async
        raise RuntimeError("No emitter set")

    def set_emitter(self, emitter: EventEmitter) -> None:
        """Set or replace the emitter. Re-injects onto all registered components."""
        self._emitter = emitter
        for handler in self._handlers.values():
            handler.emit = emitter.emit
            handler.emit_async = emitter.emit_async

    def register(self, ref: str, handler: Any, meta: ComponentMeta) -> None:
        """Register a component handler with its metadata.

        Injects emit/emit_async onto the handler and sets parent to this
        registry so the handler can call self.parent.emit_async(...).
        """
        self._handlers[ref] = handler
        self._metadata[ref] = meta
        if self._emitter:
            handler.emit = self._emitter.emit
            handler.emit_async = self._emitter.emit_async
        # Set parent to registry so self.parent.emit_async works.
        handler.parent = self

    def unregister(self, ref: str) -> None:
        """Remove a component handler."""
        self._handlers.pop(ref, None)
        self._metadata.pop(ref, None)

    def get_handler(self, ref: str) -> Any | None:
        """Get a component handler by ref."""
        return self._handlers.get(ref)

    def get_metadata(self, ref: str) -> ComponentMeta | None:
        """Get component metadata by ref."""
        return self._metadata.get(ref)

    def get_component_list(self) -> list[dict[str, Any]]:
        """Return the component list for registration with the engine."""
        components: list[dict[str, Any]] = []
        for ref, meta in self._metadata.items():
            components.append({
                "ref": ref,
                "function": meta.function.value if meta.function else None,
                "queries": list(meta.queries.keys()),
                "commands": list(meta.invokes.keys()),
                "events": list(meta.subscribes.keys()),
                "parameters": meta.parameters,
            })
        return components

    def get_profile(self) -> dict[str, Any]:
        """Return a profile dict for this registry's components."""
        component_ids: list[str] = []
        component_profiles: list[dict[str, Any]] = []
        for ref, meta in self._metadata.items():
            component_ids.append(ref)
            component_profiles.append({
                "identifier": {
                    "authority": "OpenRoIS",
                    "code": ref,
                    "codebook_ref": "",
                    "version": "",
                },
                "function": meta.function.value if meta.function else None,
                "query_profiles": [{"name": q} for q in meta.queries],
                "command_profiles": [{"name": c} for c in meta.invokes],
                "event_profiles": [{"name": e} for e in meta.subscribes],
                "parameter_profiles": meta.parameters,
            })
        return {
            "component_ids": component_ids,
            "component_profiles": component_profiles,
        }

    async def connect_all(self) -> None:
        """Call connect() on all components that define it.

        Logs and continues on per-component errors so one failing
        component does not block the rest.
        """
        for ref, handler in self._handlers.items():
            connect = getattr(handler, "connect", None)
            if connect and asyncio.iscoroutinefunction(connect):
                try:
                    await connect()
                except Exception as exc:
                    logger.warning("Connect error for %s: %s", ref, exc)

    async def disconnect_all(self) -> None:
        """Call disconnect() on all components that define it.

        Logs and continues on per-component errors so one failing
        disconnect does not block the rest.
        """
        for ref, handler in self._handlers.items():
            disconnect = getattr(handler, "disconnect", None)
            if disconnect and asyncio.iscoroutinefunction(disconnect):
                try:
                    await disconnect()
                except Exception as exc:
                    logger.warning("Disconnect error for %s: %s", ref, exc)

    def get_rclpy_nodes(self) -> list:
        """Collect all rclpy.Node instances from registered components."""
        nodes = []
        for handler in self._handlers.values():
            node = getattr(handler, "node", None)
            if node is not None:
                nodes.append(node)
        return nodes

    # -- ComponentContract implementation (for local dispatch) --

    async def discover(self, condition: str = "") -> dict[str, Any]:
        """Return all local component refs."""
        return {
            "return_code": ReturnCode.OK.value,
            "component_ref_list": list(self._handlers.keys()),
        }

    async def invoke(
        self,
        bare_ref: str,
        command_type: str,
        command_id: str,
        parameters: list[Any],
    ) -> dict[str, Any]:
        """Dispatch an invoke (command) to a local component handler."""
        handler = self._handlers.get(bare_ref)
        if not handler:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "command_id": ""}

        meta = self._metadata.get(bare_ref)
        if not meta:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "command_id": ""}

        method_name = meta.invokes.get(command_type)
        if not method_name:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "command_id": ""}

        method = getattr(handler, method_name)
        try:
            response = await method(parameters)
            return {
                "return_code": response.return_code.value,
                "command_id": response.command_id,
            }
        except Exception as exc:
            logger.error("Invoke error for %s/%s: %s", bare_ref, command_type, exc)
            return {"return_code": ReturnCode.ERROR.value, "command_id": ""}

    async def query(
        self,
        bare_ref: str,
        query_type: str,
        condition: str = "",
    ) -> dict[str, Any]:
        """Dispatch a query to a local component handler."""
        handler = self._handlers.get(bare_ref)
        if not handler:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "results": []}

        meta = self._metadata.get(bare_ref)
        if not meta:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "results": []}

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
            logger.error("Query error for %s/%s: %s", bare_ref, query_type, exc)
            return {"return_code": ReturnCode.ERROR.value, "results": []}

    async def subscribe(
        self,
        bare_ref: str,
        event_type: str,
        condition: str = "",
    ) -> dict[str, Any]:
        """Register a subscription and call the component's subscribe handler."""
        if not self._emitter:
            return {"return_code": ReturnCode.ERROR.value, "subscribe_id": ""}

        handler = self._handlers.get(bare_ref)
        if not handler:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "subscribe_id": ""}

        meta = self._metadata.get(bare_ref)
        if not meta:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "subscribe_id": ""}

        method_name = meta.subscribes.get(event_type)
        if not method_name:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "subscribe_id": ""}

        subscribe_id = self._emitter.add_subscription(bare_ref, event_type)
        method = getattr(handler, method_name)
        try:
            await method()
        except Exception as exc:
            logger.error("Subscribe error for %s/%s: %s", bare_ref, event_type, exc)
            self._emitter.remove_subscription(subscribe_id)
            return {"return_code": ReturnCode.ERROR.value, "subscribe_id": ""}

        return {
            "return_code": ReturnCode.OK.value,
            "subscribe_id": subscribe_id,
        }

    async def unsubscribe(self, subscribe_id: str) -> dict[str, Any]:
        """Remove a subscription."""
        if not self._emitter:
            return {"return_code": ReturnCode.ERROR.value}
        self._emitter.remove_subscription(subscribe_id)
        return {"return_code": ReturnCode.OK.value}


# ---------------------------------------------------------------------------
# SubEngine
# ---------------------------------------------------------------------------


class SubEngine:
    """Proxy for a remote child engine connected via WebSocket.

    Implements the ComponentContract protocol by forwarding JSON-RPC
    requests over WebSocket and awaiting matching responses. Event
    notifications from the adapter are routed to the EventSink associated
    with the subscribe_id.

    Multiple SubEngine instances can exist simultaneously, one per
    connected adapter.
    """

    def __init__(
        self,
        ws_send: Callable[[str], Awaitable[None]],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._ws_send = ws_send
        self._loop = loop
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._event_sinks: dict[str, Callable[[dict], Awaitable[None]]] = {}
        self._next_id = 0

        self.engine_id = ""
        self.platform = ""
        self.components: list[dict[str, Any]] = []

    @property
    def is_connected(self) -> bool:
        """Whether the WebSocket is open."""
        return self._ws_send is not None

    def attach_websocket(
        self,
        ws_send: Callable[[str], Awaitable[None]],
    ) -> None:
        """Attach a WebSocket send function."""
        self._ws_send = ws_send

    def detach_websocket(self) -> None:
        """Detach the WebSocket and reject all pending requests."""
        self._ws_send = None
        for future in self._pending.values():
            if not future.done():
                future.set_result({"return_code": ReturnCode.ERROR.value})
        self._pending.clear()
        self._event_sinks.clear()

    def handle_register(self, msg: dict) -> None:
        """Process rois.adapter.register and cache engine_id + components."""
        params = msg.get("params", {})
        self.engine_id = str(params.get("engine_id", ""))
        self.platform = str(params.get("platform", ""))
        raw_components = params.get("components", [])
        self.components = [
            {
                "ref": str(c.get("ref", "")),
                "function": c.get("function"),
                "queries": c.get("queries", []),
                "commands": c.get("commands", []),
                "events": c.get("events", []),
                "parameters": c.get("parameters", []),
            }
            for c in raw_components
        ]
        logger.info(
            "Registered sub-engine %s (platform: %s) with %d components",
            self.engine_id,
            self.platform or "unknown",
            len(self.components),
        )

    def handle_response(self, msg: dict) -> None:
        """Called by WsServer when a response arrives from the child engine."""
        request_id = str(msg.get("id", ""))
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(msg.get("result", {}))

    async def handle_notification(self, msg: dict) -> None:
        """Called by WsServer when an event notify arrives from the child engine."""
        params = msg.get("params", {})
        subscribe_id = str(params.get("subscribe_id", ""))
        sink = self._event_sinks.get(subscribe_id)
        if sink:
            try:
                await sink(params)
            except Exception as exc:
                logger.error("Event sink error: %s", exc)

    async def send_request(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Forward a JSON-RPC request to the child engine and await response."""
        if not self.is_connected:
            return {"return_code": ReturnCode.ERROR.value}

        self._next_id += 1
        request_id = f"req-{self._next_id}"
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future[dict] = self._loop.create_future()
        self._pending[request_id] = future

        try:
            await self._ws_send(json.dumps(message))
        except Exception as exc:
            self._pending.pop(request_id, None)
            logger.error("WS send error: %s", exc)
            return {"return_code": ReturnCode.ERROR.value}

        try:
            return await asyncio.wait_for(future, timeout=10.0)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            return {"return_code": ReturnCode.TIMEOUT.value}
        finally:
            self._pending.pop(request_id, None)

    # -- ComponentContract implementation (for remote dispatch) --

    async def invoke(
        self,
        component_ref: str,
        command_type: str,
        command_id: str,
        parameters: list[Any],
    ) -> dict[str, Any]:
        """Forward an invoke request to the child engine."""
        result = await self.send_request("rois.command.execute", {
            "component_ref": component_ref,
            "command_type": command_type,
            "parameters": parameters,
        })
        return {
            "return_code": result.get("return_code", ReturnCode.ERROR.value),
            "command_id": result.get("command_id", ""),
        }

    async def query(
        self,
        component_ref: str,
        query_type: str,
        condition: str = "",
    ) -> dict[str, Any]:
        """Forward a query request to the child engine."""
        result = await self.send_request("rois.query.query", {
            "component_ref": component_ref,
            "query_type": query_type,
            "condition": condition,
        })
        return {
            "return_code": result.get("return_code", ReturnCode.ERROR.value),
            "results": result.get("results", []),
        }

    async def subscribe(
        self,
        component_ref: str,
        event_type: str,
        condition: str,
        sink: Callable[[dict], Awaitable[None]],
    ) -> dict[str, Any]:
        """Forward a subscribe request to the child engine."""
        result = await self.send_request("rois.event.subscribe", {
            "component_ref": component_ref,
            "event_type": event_type,
            "condition": condition,
        })
        subscribe_id = result.get("subscribe_id", "")
        if subscribe_id:
            self._event_sinks[subscribe_id] = sink
        return {
            "return_code": result.get("return_code", ReturnCode.ERROR.value),
            "subscribe_id": subscribe_id,
        }

    async def unsubscribe(self, subscribe_id: str) -> dict[str, Any]:
        """Forward an unsubscribe request to the child engine."""
        result = await self.send_request("rois.event.unsubscribe", {
            "subscribe_id": subscribe_id,
        })
        self._event_sinks.pop(subscribe_id, None)
        return {"return_code": result.get("return_code", ReturnCode.ERROR.value)}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class Engine:
    """The recursive HRI engine.

    Manages HRI components. Routes RoIS JSON-RPC calls to child engines
    (sub-engines) or local components based on component ref. Implements
    the five RoIS interfaces: System, Command, Query, Event, Streaming.

    When hosted by the gateway: has child engines (SubEngine proxies),
    optionally local components. Aggregates profiles from all sources.

    When hosted by an adapter: has local components (ComponentRegistry),
    no child engines. Registers with the parent engine over WebSocket.

    Multi-client resource allocation:
    - bind/release: tracks which client has reserved which component.
      Only the bound client can execute() on actuation components.
    """

    def __init__(
        self,
        engine_id: str = "",
        platform: str = "",
        enforce_bindings: bool = False,
    ) -> None:
        """Initialize the engine.

        Args:
            engine_id: The engine ID for this engine. Empty for the gateway.
            platform: The platform identifier (e.g., "kachaka").
            enforce_bindings: Whether to enforce bind/release on execute.
                Defaults to False (adapter mode). The main HRI Engine
                (gateway) sets this to True: only the client that called
                bind() can call execute() on actuation components.
                Adapters leave it False: the gateway already authorized
                the command, so the adapter trusts it and skips the
                redundant check. Per the RoIS spec, resource ownership
                is consolidated in the HRI Engine, not distributed
                across sub-engines.
        """
        self._engine_id = engine_id
        self._platform = platform
        self._enforce_bindings = enforce_bindings

        # Sub-engine registry: engine_id -> sub-engine entry
        self._sub_engines: dict[str, dict[str, Any]] = {}
        # Bare component ref -> engine_id that owns it
        self._component_index: dict[str, str] = {}
        # Full component ref (engineId/ref) -> client id
        self._bindings: dict[str, str] = {}

        # Local component registry
        self._component_registry = ComponentRegistry()

    @property
    def component_registry(self) -> ComponentRegistry:
        """Access the local component registry."""
        return self._component_registry

    def register_component(
        self,
        ref: str,
        handler: Any,
        meta: ComponentMeta,
    ) -> None:
        """Register a local component handler."""
        self._component_registry.register(ref, handler, meta)

    def register_sub_engine(
        self,
        engine_id: str,
        components: list[dict[str, Any]],
        sub_engine: SubEngine,
        platform: str = "",
    ) -> None:
        """Register a sub-engine and its components."""
        self._sub_engines[engine_id] = {
            "engine_id": engine_id,
            "platform": platform,
            "components": components,
            "sub_engine": sub_engine,
        }
        self._rebuild_index()

    def unregister_sub_engine(self, engine_id: str) -> None:
        """Remove a sub-engine (when its WebSocket disconnects)."""
        self._sub_engines.pop(engine_id, None)
        self._rebuild_index()
        # Release all bindings for this sub-engine's components.
        to_remove = [
            ref for ref in self._bindings
            if ref.startswith(f"{engine_id}/")
        ]
        for ref in to_remove:
            del self._bindings[ref]

    def release_all(self, client_id: str) -> None:
        """Release all components bound by a client."""
        to_remove = [
            ref for ref, owner in self._bindings.items()
            if owner == client_id
        ]
        for ref in to_remove:
            del self._bindings[ref]

    def get_sub_engines(self) -> list[dict[str, Any]]:
        """Get all registered sub-engine entries."""
        return list(self._sub_engines.values())

    def get_components(self) -> list[dict[str, Any]]:
        """Get all registered components across all sub-engines and local."""
        result = []
        # Local components
        for ref in self._component_registry._metadata:
            result.append({"engine_id": self._engine_id, "component": ref})
        # Sub-engine components
        for entry in self._sub_engines.values():
            for c in entry["components"]:
                result.append({
                    "engine_id": entry["engine_id"],
                    "component": c,
                })
        return result

    def get_bindings(self) -> list[dict[str, str]]:
        """Get the current bindings."""
        return [
            {"component_ref": ref, "client_id": client_id}
            for ref, client_id in self._bindings.items()
        ]

    async def dispatch(
        self,
        method: str,
        params: dict[str, Any],
        sink: Callable[[dict], Awaitable[None]] | None = None,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch a JSON-RPC method to the appropriate handler.

        Returns a result dict for the JSON-RPC response.
        """
        logger.debug("[engine] %s %s", method, json.dumps(params))

        if method == "rois.system.connect":
            return {"return_code": ReturnCode.OK.value}

        if method == "rois.system.disconnect":
            self.release_all(client_id or "")
            return {"return_code": ReturnCode.OK.value}

        if method == "rois.system.get_profile":
            return await self._handle_get_profile()

        if method == "rois.command.search":
            return await self._handle_search()

        if method == "rois.command.bind":
            return self._handle_bind(params, client_id)

        if method == "rois.command.release":
            return self._handle_release(params, client_id)

        if method == "rois.command.execute":
            return await self._handle_execute(params, client_id)

        if method == "rois.command.set_parameter":
            return await self._handle_set_parameter(params, client_id)

        if method == "rois.query.query":
            return await self._handle_query(params)

        if method == "rois.event.subscribe":
            return await self._handle_subscribe(params, sink)

        if method == "rois.event.unsubscribe":
            return await self._handle_unsubscribe(params)

        return {"return_code": ReturnCode.UNSUPPORTED.value}

    # -- Handlers --

    async def _handle_search(self) -> dict[str, Any]:
        refs: list[str] = []
        # Local components (no prefix)
        for ref in self._component_registry._metadata:
            refs.append(ref)
        # Sub-engine components (with engine_id prefix)
        for entry in self._sub_engines.values():
            for c in entry["components"]:
                refs.append(f"{entry['engine_id']}/{c['ref']}")
        return {
            "return_code": ReturnCode.OK.value,
            "component_ref_list": refs,
        }

    async def _handle_get_profile(self) -> dict[str, Any]:
        component_ids: list[str] = []
        component_profiles: list[dict[str, Any]] = []

        # Local components
        local_profile = self._component_registry.get_profile()
        for cid in local_profile["component_ids"]:
            component_ids.append(cid)
        component_profiles.extend(local_profile["component_profiles"])

        # Sub-engine components
        for entry in self._sub_engines.values():
            for c in entry["components"]:
                full_ref = f"{entry['engine_id']}/{c['ref']}"
                component_ids.append(full_ref)
                component_profiles.append({
                    "identifier": {
                        "authority": "OpenRoIS",
                        "code": c["ref"],
                        "codebook_ref": "",
                        "version": "",
                    },
                    "name": c["ref"],
                    "function": c.get("function"),
                    "command_profiles": [{"name": name, "results": []} for name in c.get("commands", [])],
                    "query_profiles": [{"name": name, "results": []} for name in c.get("queries", [])],
                    "event_profiles": [{"name": name, "results": []} for name in c.get("events", [])],
                    "parameter_profiles": c.get("parameters", []),
                })

        return {
            "return_code": ReturnCode.OK.value,
            "profile": {
                "identifier": {
                    "authority": "OpenRoIS",
                    "code": self._engine_id or "Engine",
                    "codebook_ref": "",
                    "version": "",
                },
                "sub_engine_ids": list(self._sub_engines.keys()),
                "component_ids": component_ids,
                "component_profiles": component_profiles,
            },
        }

    def _handle_bind(
        self,
        params: dict[str, Any],
        client_id: str | None,
    ) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        component = self._find_component(component_ref)
        if not component:
            return {"return_code": ReturnCode.UNSUPPORTED.value}
        # Derive binding requirement from function and commands.
        if isinstance(component, dict):
            function = component.get("function")
            commands = component.get("commands", [])
        else:
            function = component.function.value if component.function else None
            commands = list(component.invokes.keys()) if hasattr(component, "invokes") else []
        if not _requires_bind(function, commands):
            return {"return_code": ReturnCode.OK.value}
        current_owner = self._bindings.get(component_ref)
        if current_owner and current_owner != client_id:
            return {"return_code": ReturnCode.OUT_OF_RESOURCES.value}
        self._bindings[component_ref] = client_id or ""
        return {"return_code": ReturnCode.OK.value}

    def _handle_release(
        self,
        params: dict[str, Any],
        client_id: str | None,
    ) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        if self._bindings.get(component_ref) == (client_id or ""):
            self._bindings.pop(component_ref, None)
        return {"return_code": ReturnCode.OK.value}

    async def _handle_execute(
        self,
        params: dict[str, Any],
        client_id: str | None,
    ) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        component = self._find_component(component_ref)
        if not component:
            return {"return_code": ReturnCode.UNSUPPORTED.value}

        # Derive binding requirement from function and commands.
        if isinstance(component, dict):
            function = component.get("function")
            commands = component.get("commands", [])
        else:
            function = component.function.value if component.function else None
            commands = list(component.invokes.keys()) if hasattr(component, "invokes") else []
        if _requires_bind(function, commands):
            if self._enforce_bindings:
                if self._bindings.get(component_ref) != (client_id or ""):
                    return {"return_code": ReturnCode.OUT_OF_RESOURCES.value}

        # Support both spec structured format (command_unit_list) and
        # legacy flat format (command_type + parameters).
        unit_list = params.get("command_unit_list", [])
        if isinstance(unit_list, list) and len(unit_list) > 0:
            unit = unit_list[0]
            command_type = str(unit.get("command_type", "execute"))
            raw_params = unit.get("arguments", [])
            bare_ref = str(unit.get("component_ref", component_ref))
        else:
            command_type = str(params.get("command_type", "execute"))
            raw_params = params.get("parameters", params.get("arguments", []))
            bare_ref = component_ref

        bare_ref = bare_ref.split("/", 1)[1] if "/" in bare_ref else bare_ref

        # Try local first
        if bare_ref in self._component_registry._handlers:
            return await self._component_registry.invoke(
                bare_ref, command_type, "", raw_params,
            )

        # Forward to sub-engine
        sub_engine = self._find_sub_engine(component_ref)
        if not sub_engine:
            return {"return_code": ReturnCode.UNSUPPORTED.value}
        return await sub_engine.invoke(component_ref, command_type, "", raw_params)

    async def _handle_set_parameter(
        self,
        params: dict[str, Any],
        client_id: str | None,
    ) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        bare_ref = component_ref.split("/", 1)[1] if "/" in component_ref else component_ref

        # Try local first
        if bare_ref in self._component_registry._handlers:
            return await self._component_registry.invoke(
                bare_ref, "set_parameter", "", params.get("parameters", []),
            )

        sub_engine = self._find_sub_engine(component_ref)
        if not sub_engine:
            return {"return_code": ReturnCode.UNSUPPORTED.value}
        return await sub_engine.invoke(
            component_ref, "set_parameter", "", params.get("parameters", []),
        )

    async def _handle_query(self, params: dict[str, Any]) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        query_type = str(params.get("query_type", ""))
        condition = str(params.get("condition", ""))
        bare_ref = component_ref.split("/", 1)[1] if "/" in component_ref else component_ref

        # Try local first
        if bare_ref in self._component_registry._handlers:
            return await self._component_registry.query(bare_ref, query_type, condition)

        sub_engine = self._find_sub_engine(component_ref)
        if not sub_engine:
            return {"return_code": ReturnCode.UNSUPPORTED.value}
        return await sub_engine.query(component_ref, query_type, condition)

    async def _handle_subscribe(
        self,
        params: dict[str, Any],
        sink: Callable[[dict], Awaitable[None]] | None,
    ) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        event_type = str(params.get("event_type", ""))
        condition = str(params.get("condition", ""))
        bare_ref = component_ref.split("/", 1)[1] if "/" in component_ref else component_ref

        # Try local first. The ComponentRegistry handles subscriptions
        # via the EventEmitter, which pushes events back through the
        # WebSocket. The sink is not needed for local components: it
        # is only used when forwarding to a remote sub-engine.
        if bare_ref in self._component_registry._handlers:
            return await self._component_registry.subscribe(
                bare_ref, event_type, condition,
            )

        # Forward to sub-engine. The sink is required for forwarding
        # because the sub-engine proxy needs a callback to deliver
        # events back to the caller.
        if not sink:
            return {"return_code": ReturnCode.ERROR.value, "subscribe_id": ""}

        sub_engine = self._find_sub_engine(component_ref)
        if not sub_engine:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "subscribe_id": ""}
        return await sub_engine.subscribe(component_ref, event_type, condition, sink)

    async def _handle_unsubscribe(self, params: dict[str, Any]) -> dict[str, Any]:
        subscribe_id = str(params.get("subscribe_id", ""))
        # Unsubscribe from local registry
        if self._component_registry._emitter:
            self._component_registry._emitter.remove_subscription(subscribe_id)
        # Unsubscribe from all sub-engines
        for entry in self._sub_engines.values():
            await entry["sub_engine"].unsubscribe(subscribe_id)
        return {"return_code": ReturnCode.OK.value}

    # -- Helpers --

    def _rebuild_index(self) -> None:
        """Rebuild the component index from sub-engines."""
        self._component_index.clear()
        for entry in self._sub_engines.values():
            for c in entry["components"]:
                self._component_index[c["ref"]] = entry["engine_id"]

    def _find_component(self, ref: str) -> dict[str, Any] | ComponentMeta | None:
        """Find a registered component by ref.

        Checks local registry first, then sub-engines. Handles both
        bare refs and engine_id-prefixed refs.
        """
        # Check local registry first (bare ref only)
        bare_ref = ref.split("/", 1)[1] if "/" in ref else ref
        local_meta = self._component_registry.get_metadata(bare_ref)
        if local_meta:
            return local_meta

        # Check sub-engines
        if "/" in ref:
            slash_idx = ref.index("/")
            engine_id = ref[:slash_idx]
            bare = ref[slash_idx + 1:]
            entry = self._sub_engines.get(engine_id)
            if entry:
                for c in entry["components"]:
                    if c["ref"] == bare:
                        return c
            return None

        # Bare ref: search all sub-engines
        for entry in self._sub_engines.values():
            for c in entry["components"]:
                if c["ref"] == ref:
                    return c
        return None

    def _find_sub_engine(self, ref: str) -> SubEngine | None:
        """Find the SubEngine that owns a component ref."""
        if "/" in ref:
            slash_idx = ref.index("/")
            engine_id = ref[:slash_idx]
            bare = ref[slash_idx + 1:]
            entry = self._sub_engines.get(engine_id)
            if entry and any(c["ref"] == bare for c in entry["components"]):
                return entry["sub_engine"]
            return None

        engine_id = self._component_index.get(ref)
        if not engine_id:
            return None
        entry = self._sub_engines.get(engine_id)
        return entry["sub_engine"] if entry else None