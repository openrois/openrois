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
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from openrois.interfaces.bus import (
    CommandRequest,
    ComponentContract,
    DiscoverRequest,
    DiscoverResponse,
    EventEnvelope,
    EventSink,
    InvokeResponse,
    QueryRequest,
    QueryResponse,
    SubscribeRequest,
    SubscribeResponse,
)
from openrois.interfaces.common import StreamStatus
from openrois.interfaces.hri import CommandType, Parameter, Result, ReturnCode
from openrois.interfaces.service import CompletedStatus, ErrorType

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


COMPLETED = "completed"
NOTIFY_ERROR = "notify_error"
STREAM_STATUS = "notify_stream_status"
DETAIL_LIMIT = 256


def _result_value(results: list[Result], name: str) -> str:
    for r in results:
        if r.name == name:
            return r.value
    return ""


def envelope_to_params(envelope: EventEnvelope) -> dict[str, Any]:
    """Map an EventEnvelope to the params of a rois.event.notify notification."""
    return {
        "event_id": envelope.event_id,
        "subscribe_id": envelope.subscribe_id,
        "component_ref": envelope.component_ref,
        "event_type": envelope.event_type,
        "expire": envelope.expire,
        "results": [r.model_dump() for r in envelope.payload],
    }


def envelope_to_notification(envelope: EventEnvelope) -> dict[str, Any]:
    """Map an EventEnvelope to the JSON-RPC notification that carries it.

    Component events travel as rois.event.notify. Command completions and
    engine errors are envelopes too (RoIS_Service completed and notify_error),
    and go out as rois.command.completed and rois.system.notify_error.
    """
    if envelope.event_type == COMPLETED:
        payload = [r.model_dump() for r in envelope.payload if r.name != "command_id"]
        return {
            "jsonrpc": "2.0",
            "method": "rois.command.completed",
            "params": {
                "command_id": _result_value(envelope.payload, "command_id"),
                "status": (envelope.completed_status or CompletedStatus.OK).value,
                "results": payload,
            },
        }
    if envelope.event_type == STREAM_STATUS:
        return {
            "jsonrpc": "2.0",
            "method": "rois.stream.notify_status",
            "params": {
                "stream_id": _result_value(envelope.payload, "stream_id"),
                "status": (envelope.stream_status or StreamStatus.NOT_CONNECTED).value,
                "timestamp": _result_value(envelope.payload, "timestamp"),
                "component_ref": envelope.component_ref,
            },
        }
    if envelope.event_type == NOTIFY_ERROR:
        return {
            "jsonrpc": "2.0",
            "method": "rois.system.notify_error",
            "params": {
                "error_id": envelope.event_id,
                "error_type": (envelope.error_type or ErrorType.ENGINE_INTERNAL_ERROR).value,
                "command_id": _result_value(envelope.payload, "command_id"),
                "message": _result_value(envelope.payload, "message"),
            },
        }
    return {"jsonrpc": "2.0", "method": "rois.event.notify", "params": envelope_to_params(envelope)}


def params_to_envelope(params: dict[str, Any]) -> EventEnvelope:
    """Build an EventEnvelope from the params of a rois.event.notify notification."""
    return EventEnvelope(
        event_id=str(params.get("event_id", "")) or str(uuid.uuid4()),
        event_type=str(params.get("event_type", "")),
        subscribe_id=str(params.get("subscribe_id", "")),
        component_ref=str(params.get("component_ref", "")),
        expire=str(params.get("expire", "")),
        payload=[Result.model_validate(r) for r in params.get("results", [])],
    )


def completion_envelope(
    command_id: str,
    status: CompletedStatus,
    results: list[Result] | None = None,
) -> EventEnvelope:
    """The envelope of a RoIS_Service completed notification."""
    return EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type=COMPLETED,
        completed_status=status,
        payload=[
            Result(name="command_id", data_type_ref="string", value=command_id),
            *(results or []),
        ],
    )


def error_envelope(error_type: ErrorType, message: str, command_id: str = "") -> EventEnvelope:
    """The envelope of a RoIS_Service notify_error notification."""
    payload = [Result(name="message", data_type_ref="string", value=message)]
    if command_id:
        payload.append(Result(name="command_id", data_type_ref="string", value=command_id))
    return EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type=NOTIFY_ERROR,
        error_type=error_type,
        payload=payload,
    )


def notification_to_envelope(msg: dict[str, Any]) -> EventEnvelope | None:
    """Inverse of envelope_to_notification for the three notification methods."""
    method = msg.get("method")
    params = msg.get("params", {}) or {}
    if method == "rois.event.notify":
        return params_to_envelope(params)
    if method == "rois.command.completed":
        try:
            status = CompletedStatus(str(params.get("status", "OK")))
        except ValueError:
            status = CompletedStatus.ERROR
        return completion_envelope(
            str(params.get("command_id", "")), status,
            [Result.model_validate(r) for r in params.get("results", [])],
        )
    if method == "rois.stream.notify_status":
        try:
            stream_status = StreamStatus(str(params.get("status", "")))
        except ValueError:
            stream_status = StreamStatus.NOT_CONNECTED
        stream_id = str(params.get("stream_id", ""))
        timestamp = str(params.get("timestamp", ""))
        return EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type=STREAM_STATUS,
            component_ref=str(params.get("component_ref", "")),
            stream_status=stream_status,
            payload=[
                Result(name="stream_id", data_type_ref="string", value=stream_id),
                Result(name="timestamp", data_type_ref="DateTime", value=timestamp),
                Result(name="status", data_type_ref="Stream_Status", value=stream_status.value),
            ],
        )
    if method == "rois.system.notify_error":
        try:
            error_type = ErrorType(str(params.get("error_type", "")))
        except ValueError:
            error_type = ErrorType.ENGINE_INTERNAL_ERROR
        envelope = error_envelope(
            error_type, str(params.get("message", "")), str(params.get("command_id", "")),
        )
        error_id = str(params.get("error_id", ""))
        return envelope.model_copy(update={"event_id": error_id}) if error_id else envelope
    return None


def _stream_status_of(event_type: str, results: list[Result]) -> StreamStatus | None:
    """The typed stream status of a notify_stream_status event, read from its results."""
    if event_type != STREAM_STATUS:
        return None
    try:
        return StreamStatus(_result_value(results, "status"))
    except ValueError:
        return StreamStatus.NOT_CONNECTED


def _remember(store: OrderedDict[str, Any], key: str, value: Any) -> None:
    """Keep the last DETAIL_LIMIT entries so detail lookups stay bounded."""
    store[key] = value
    while len(store) > DETAIL_LIMIT:
        store.popitem(last=False)


def _accepts_argument(method: Any) -> bool:
    """Whether a bound handler takes one positional argument besides self."""
    import inspect

    try:
        parameters = [
            p for p in inspect.signature(method).parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
    except (TypeError, ValueError):
        return False
    return len(parameters) >= 1


def _bare_ref(component_ref: str) -> str:
    """Strip the engine_id prefix of a component ref, if any."""
    return component_ref.split("/", 1)[1] if "/" in component_ref else component_ref


def parameter_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a decorator parameter dict to the RoIS ParameterProfile shape.

    Components declare data_type_ref as a plain code ("string[]"); the profile
    carries a RoISIdentifierType.
    """
    ref = raw.get("data_type_ref", "")
    if not isinstance(ref, dict):
        ref = {"authority": "", "code": str(ref), "codebook_ref": "", "version": ""}
    return {
        "name": str(raw.get("name", "")),
        "data_type_ref": ref,
        "default_value": str(raw.get("default_value", "")),
        "description": str(raw.get("description", "")),
    }


def _to_parameters(raw: list[Any]) -> list[Parameter]:
    """Validate raw parameter dicts into Parameter models.

    Accepts the RoIS shape (name, data_type_ref, value) as dicts or models.
    Entries that do not validate are skipped, with a log line, rather than
    failing the whole command: the component decides what it needs.
    """
    parameters: list[Parameter] = []
    for item in raw or []:
        try:
            parameters.append(
                item if isinstance(item, Parameter) else Parameter.model_validate(item)
            )
        except Exception as exc:
            logger.warning("Ignoring malformed parameter %r: %s", item, exc)
    return parameters


async def _deliver(sink: EventSink, envelope: EventEnvelope) -> None:
    """Await one delivery, logging instead of raising: emit() has no caller to tell."""
    try:
        await sink(envelope)
    except Exception as exc:
        logger.error("Event sink error for %s: %s", envelope.event_type, exc)


class EventEmitter:
    """Delivers component events to the sinks of active subscriptions.

    Each subscription pairs a (component_ref, event_type) with the EventSink
    that the subscriber passed to ComponentContract.subscribe(). emit() is
    thread-safe: a component can call it from a background thread (an rclpy
    callback), and delivery is scheduled on the asyncio loop. emit_async() is
    for callers that already run on the loop.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        # subscribe_id -> (component_ref, event_type, sink)
        self._subscriptions: dict[str, tuple[str, str, EventSink]] = {}
        # command_id -> sink of the caller waiting for its completion
        self._commands: dict[str, EventSink] = {}

    def add_subscription(self, component_ref: str, event_type: str, sink: EventSink) -> str:
        """Register a subscription and return its subscribe_id."""
        subscribe_id = str(uuid.uuid4())
        self._subscriptions[subscribe_id] = (component_ref, event_type, sink)
        return subscribe_id

    def remove_subscription(self, subscribe_id: str) -> bool:
        """Remove a subscription. Returns False if it did not exist."""
        return self._subscriptions.pop(subscribe_id, None) is not None

    def remove_all_subscriptions(self) -> None:
        """Drop every subscription, for example when the transport closes."""
        self._subscriptions.clear()

    def has_subscription(self, subscribe_id: str) -> bool:
        """Whether a subscribe_id belongs to this emitter."""
        return subscribe_id in self._subscriptions

    def has_subscribers(self, component_ref: str, event_type: str) -> bool:
        """Whether anyone subscribed to this component event."""
        return any(
            (cref, etype) == (component_ref, event_type)
            for cref, etype, _ in self._subscriptions.values()
        )

    def _deliveries(
        self,
        component_ref: str,
        event_type: str,
        results: list[Result],
    ) -> list[tuple[EventSink, EventEnvelope]]:
        return [
            (
                sink,
                EventEnvelope(
                    event_id=str(uuid.uuid4()),
                    event_type=event_type,
                    subscribe_id=subscribe_id,
                    component_ref=component_ref,
                    stream_status=_stream_status_of(event_type, results),
                    payload=list(results),
                ),
            )
            for subscribe_id, (cref, etype, sink) in self._subscriptions.items()
            if cref == component_ref and etype == event_type
        ]

    def emit(
        self,
        component_ref: str,
        event_type: str,
        results: list[Result],
    ) -> None:
        """Emit an event from any thread. No-op without subscribers."""
        for sink, envelope in self._deliveries(component_ref, event_type, results):
            asyncio.run_coroutine_threadsafe(_deliver(sink, envelope), self._loop)

    async def emit_async(
        self,
        component_ref: str,
        event_type: str,
        results: list[Result],
    ) -> None:
        """Emit an event from the asyncio loop. No-op without subscribers."""
        for sink, envelope in self._deliveries(component_ref, event_type, results):
            try:
                await sink(envelope)
            except Exception as exc:
                logger.error("Event sink error for %s/%s: %s", component_ref, event_type, exc)

    # -- Command completion --

    def track_command(self, command_id: str, sink: EventSink) -> None:
        """Remember who to tell when a command completes."""
        if command_id:
            self._commands[command_id] = sink

    def complete(
        self,
        command_id: str,
        status: CompletedStatus | str = CompletedStatus.OK,
        results: list[Result] | None = None,
    ) -> None:
        """Report a command's completion from any thread. No-op if nobody waits."""
        sink = self._commands.pop(command_id, None)
        if sink is None:
            return
        envelope = completion_envelope(command_id, CompletedStatus(status), results)
        asyncio.run_coroutine_threadsafe(_deliver(sink, envelope), self._loop)

    async def complete_async(
        self,
        command_id: str,
        status: CompletedStatus | str = CompletedStatus.OK,
        results: list[Result] | None = None,
    ) -> None:
        """Report a command's completion from the asyncio loop."""
        sink = self._commands.pop(command_id, None)
        if sink is None:
            return
        await _deliver(sink, completion_envelope(command_id, CompletedStatus(status), results))


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

    @property
    def complete(self) -> Callable[..., None]:
        """Thread-safe command completion, delegates to EventEmitter."""
        if self._emitter:
            return self._emitter.complete
        raise RuntimeError("No emitter set")

    @property
    def complete_async(self) -> Callable[..., Awaitable[None]]:
        """Async command completion, delegates to EventEmitter."""
        if self._emitter:
            return self._emitter.complete_async
        raise RuntimeError("No emitter set")

    def track_command(self, command_id: str, sink: EventSink) -> None:
        """Route the completion of a command to the caller's sink."""
        if self._emitter:
            self._emitter.track_command(command_id, sink)

    def track_stream(self, stream_id: str, sink: EventSink | None) -> None:
        """Local stream status events reach the caller through its subscription."""

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
                "name": ref,
                # OpenRoIS extension: the RoSO function class, which the gateway
                # uses to decide whether a component needs a reservation.
                "function": meta.function.value if meta.function else None,
                "query_profiles": [{"name": q, "results": []} for q in meta.queries],
                "command_profiles": [{"name": c, "results": []} for c in meta.invokes],
                "event_profiles": [{"name": e, "results": []} for e in meta.subscribes],
                "parameter_profiles": [parameter_profile(p) for p in meta.parameters],
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

    def get_rclpy_nodes(self) -> list[Any]:
        """Collect all rclpy.Node instances from registered components."""
        nodes: list[Any] = []
        for handler in self._handlers.values():
            node = getattr(handler, "_node", None)
            if node is not None:
                nodes.append(node)
        return nodes

    # -- ComponentContract implementation (for local dispatch) --

    # -- ComponentContract implementation (local dispatch) --

    async def discover(self, request: DiscoverRequest | None = None) -> DiscoverResponse:
        """Return the refs of all local components."""
        return DiscoverResponse(component_ref_list=list(self._handlers.keys()))

    async def invoke(self, request: CommandRequest) -> InvokeResponse:
        """Dispatch a command to a local component handler.

        The handler receives the parameters as plain dictionaries with the
        RoIS shape (name, data_type_ref, value), which keeps component code
        free of Pydantic imports.
        """
        bare_ref = _bare_ref(request.component_ref)
        handler = self._handlers.get(bare_ref)
        meta = self._metadata.get(bare_ref)
        if handler is None or meta is None:
            return InvokeResponse(return_code=ReturnCode.UNSUPPORTED)

        method_name = meta.invokes.get(str(request.command_type))
        if not method_name:
            return InvokeResponse(return_code=ReturnCode.UNSUPPORTED)

        arguments = request.parameters or request.arguments
        raw = [a.model_dump() for a in arguments]
        method = getattr(handler, method_name)
        try:
            response = await method(raw)
        except Exception as exc:
            logger.error("Invoke error for %s/%s: %s", bare_ref, request.command_type, exc)
            return InvokeResponse(return_code=ReturnCode.ERROR)
        if isinstance(response, InvokeResponse):
            return response
        if response is None:
            return InvokeResponse(command_id=request.command_id)
        return InvokeResponse.model_validate(response)

    async def query(self, request: QueryRequest) -> QueryResponse:
        """Dispatch a query to a local component handler."""
        bare_ref = _bare_ref(request.component_ref)
        handler = self._handlers.get(bare_ref)
        meta = self._metadata.get(bare_ref)
        if handler is None or meta is None:
            return QueryResponse(return_code=ReturnCode.UNSUPPORTED)

        method_name = meta.queries.get(request.query_type)
        if not method_name:
            return QueryResponse(return_code=ReturnCode.UNSUPPORTED)

        method = getattr(handler, method_name)
        try:
            # Query handlers take no argument, except those declared with one
            # (get_stream_status), which receive the condition.
            if _accepts_argument(method):
                results = await method(request.condition)
            else:
                results = await method()
        except Exception as exc:
            logger.error("Query error for %s/%s: %s", bare_ref, request.query_type, exc)
            return QueryResponse(return_code=ReturnCode.ERROR)
        return QueryResponse(
            results=[r if isinstance(r, Result) else Result.model_validate(r) for r in results],
        )

    async def subscribe(self, request: SubscribeRequest, sink: EventSink) -> SubscribeResponse:
        """Register a subscription and call the component's subscribe handler.

        Events emitted by the component for this subscription reach the sink
        through the EventEmitter.
        """
        if not self._emitter:
            logger.warning("[registry.subscribe] no emitter set")
            return SubscribeResponse(return_code=ReturnCode.ERROR)

        bare_ref = _bare_ref(request.component_ref)
        handler = self._handlers.get(bare_ref)
        meta = self._metadata.get(bare_ref)
        if handler is None or meta is None:
            return SubscribeResponse(return_code=ReturnCode.UNSUPPORTED)

        method_name = meta.subscribes.get(request.event_type)
        if not method_name:
            return SubscribeResponse(return_code=ReturnCode.UNSUPPORTED)

        subscribe_id = self._emitter.add_subscription(bare_ref, request.event_type, sink)
        method = getattr(handler, method_name)
        try:
            await method()
        except Exception as exc:
            logger.error("[registry.subscribe] handler error for %s/%s: %s",
                         bare_ref, request.event_type, exc)
            self._emitter.remove_subscription(subscribe_id)
            return SubscribeResponse(return_code=ReturnCode.ERROR)
        return SubscribeResponse(subscribe_id=subscribe_id)

    async def unsubscribe(self, subscribe_id: str) -> ReturnCode:
        """Remove a subscription."""
        if not self._emitter:
            return ReturnCode.ERROR
        self._emitter.remove_subscription(subscribe_id)
        return ReturnCode.OK

    def owns_subscription(self, subscribe_id: str) -> bool:
        """Whether this registry holds the subscription."""
        return self._emitter is not None and self._emitter.has_subscription(subscribe_id)


# ---------------------------------------------------------------------------
# SubEngine
# ---------------------------------------------------------------------------


class SubEngine:
    """Proxy for a remote child engine connected over WebSocket.

    Implements the ComponentContract by forwarding JSON-RPC requests over
    the WebSocket and awaiting the matching responses. Event notifications
    from the child engine are routed to the EventSink registered for their
    subscribe_id.

    One SubEngine exists per connected adapter.
    """

    def __init__(
        self,
        ws_send: Callable[[str], Awaitable[None]] | None,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._ws_send = ws_send
        self._loop = loop
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._event_sinks: dict[str, EventSink] = {}
        self._command_sinks: dict[str, EventSink] = {}
        self._stream_sinks: dict[str, EventSink] = {}
        self._next_id = 0

        self.engine_id = ""
        self.platform = ""
        self.components: list[dict[str, Any]] = []

    @property
    def is_connected(self) -> bool:
        """Whether the WebSocket is open."""
        return self._ws_send is not None

    def attach_websocket(self, ws_send: Callable[[str], Awaitable[None]]) -> None:
        """Attach a WebSocket send function."""
        self._ws_send = ws_send

    def detach_websocket(self) -> None:
        """Detach the WebSocket and fail all pending requests."""
        self._ws_send = None
        for future in self._pending.values():
            if not future.done():
                future.set_result({"return_code": ReturnCode.ERROR.value})
        self._pending.clear()
        self._event_sinks.clear()

    def owns_subscription(self, subscribe_id: str) -> bool:
        """Whether this child engine holds the subscription."""
        return subscribe_id in self._event_sinks

    def remove_event_sink(self, subscribe_id: str) -> None:
        """Drop the event sink of a subscription, for example when its client left."""
        self._event_sinks.pop(subscribe_id, None)

    def track_command(self, command_id: str, sink: EventSink) -> None:
        """Route the completion or error of a command to the caller's sink."""
        if command_id:
            self._command_sinks[command_id] = sink

    def track_stream(self, stream_id: str, sink: EventSink | None) -> None:
        """Route the status notifications of a stream to the sink that connected it."""
        if sink is None:
            self._stream_sinks.pop(stream_id, None)
        elif stream_id:
            self._stream_sinks[stream_id] = sink

    # -- Transport plumbing, driven by WsServer --

    def handle_response(self, msg: dict[str, Any]) -> None:
        """Resolve the pending request that a response answers."""
        request_id = str(msg.get("id", ""))
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(msg.get("result", {}) or {})

    async def handle_notification(self, msg: dict[str, Any]) -> None:
        """Deliver a notification from the child engine to the sink that waits for it.

        Events go to their subscription's sink, completions and errors to the
        sink of the command they refer to.
        """
        envelope = notification_to_envelope(msg)
        if envelope is None:
            return
        params = msg.get("params", {}) or {}
        if envelope.event_type == COMPLETED:
            sink = self._command_sinks.pop(str(params.get("command_id", "")), None)
        elif envelope.event_type == STREAM_STATUS:
            sink = self._stream_sinks.get(str(params.get("stream_id", "")))
        elif envelope.event_type == NOTIFY_ERROR:
            sink = self._command_sinks.get(str(params.get("command_id", "")))
        else:
            sink = self._event_sinks.get(envelope.subscribe_id)
        if sink is None:
            return
        await _deliver(sink, envelope)

    async def send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Forward a JSON-RPC request to the child engine and await its result."""
        if self._ws_send is None:
            return {"return_code": ReturnCode.ERROR.value}

        self._next_id += 1
        request_id = f"req-{self._next_id}"
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}

        future: asyncio.Future[dict[str, Any]] = self._loop.create_future()
        self._pending[request_id] = future
        try:
            await self._ws_send(json.dumps(message))
        except Exception as exc:
            self._pending.pop(request_id, None)
            logger.error("WS send error: %s", exc)
            return {"return_code": ReturnCode.ERROR.value}

        try:
            return await asyncio.wait_for(future, timeout=10.0)
        except TimeoutError:
            return {"return_code": ReturnCode.TIMEOUT.value}
        finally:
            self._pending.pop(request_id, None)

    # -- ComponentContract implementation (remote dispatch) --

    async def discover(self, request: DiscoverRequest | None = None) -> DiscoverResponse:
        """Discover the child engine and cache its component list.

        Asks the child engine for its profile (rois.system.get_profile), the
        standard way to learn what an HRI Engine offers, and keeps the
        component descriptions for routing and for the aggregated profile.
        """
        result = await self.send_request("rois.system.get_profile", {})
        profile = result.get("profile", {}) or {}
        identifier = profile.get("identifier", {}) or {}
        self.engine_id = str(identifier.get("code", ""))
        self.platform = str(profile.get("platform", "") or "")
        self.components = [
            {
                "ref": str(c.get("name") or c.get("identifier", {}).get("code", "")),
                "function": c.get("function"),
                "queries": [q.get("name", "") for q in c.get("query_profiles", [])],
                "commands": [cmd.get("name", "") for cmd in c.get("command_profiles", [])],
                "events": [e.get("name", "") for e in c.get("event_profiles", [])],
                "parameters": c.get("parameter_profiles", []),
            }
            for c in profile.get("component_profiles", [])
        ]
        logger.info(
            "Discovered child engine %s (platform: %s) with %d components",
            self.engine_id, self.platform or "unknown", len(self.components),
        )
        return DiscoverResponse(
            return_code=ReturnCode(result.get("return_code", ReturnCode.ERROR.value)),
            component_ref_list=[c["ref"] for c in self.components],
        )

    async def invoke(self, request: CommandRequest) -> InvokeResponse:
        """Forward a command to the child engine."""
        arguments = request.parameters or request.arguments
        method = (
            "rois.command.set_parameter"
            if request.command_type == CommandType.SET_PARAMETER
            else "rois.command.execute"
        )
        result = await self.send_request(method, {
            "component_ref": request.component_ref,
            "command_type": str(request.command_type),
            "command_id": request.command_id,
            "parameters": [a.model_dump() for a in arguments],
        })
        return InvokeResponse(
            return_code=ReturnCode(result.get("return_code", ReturnCode.ERROR.value)),
            command_id=str(result.get("command_id", "")),
            results=[Result.model_validate(r) for r in result.get("results", [])],
        )

    async def query(self, request: QueryRequest) -> QueryResponse:
        """Forward a query to the child engine."""
        result = await self.send_request("rois.query.query", {
            "component_ref": request.component_ref,
            "query_type": request.query_type,
            "condition": request.condition,
        })
        return QueryResponse(
            return_code=ReturnCode(result.get("return_code", ReturnCode.ERROR.value)),
            results=[Result.model_validate(r) for r in result.get("results", [])],
        )

    async def subscribe(self, request: SubscribeRequest, sink: EventSink) -> SubscribeResponse:
        """Forward a subscription to the child engine and remember its sink."""
        result = await self.send_request("rois.event.subscribe", {
            "component_ref": request.component_ref,
            "event_type": request.event_type,
            "condition": request.condition,
        })
        subscribe_id = str(result.get("subscribe_id", ""))
        if subscribe_id:
            self._event_sinks[subscribe_id] = sink
        return SubscribeResponse(
            return_code=ReturnCode(result.get("return_code", ReturnCode.ERROR.value)),
            subscribe_id=subscribe_id,
        )

    async def unsubscribe(self, subscribe_id: str) -> ReturnCode:
        """Forward an unsubscribe to the child engine."""
        result = await self.send_request("rois.event.unsubscribe", {
            "subscribe_id": subscribe_id,
        })
        self._event_sinks.pop(subscribe_id, None)
        return ReturnCode(result.get("return_code", ReturnCode.ERROR.value))


def _contracts(
    registry: ComponentRegistry, sub_engine: SubEngine,
) -> tuple[ComponentContract, ComponentContract]:
    """Static check that both implementations satisfy the ComponentContract protocol."""
    return registry, sub_engine


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
        # Bounded detail stores behind get_command_result, get_event_detail,
        # get_error_detail, and get_parameter.
        self._command_results: OrderedDict[str, list[Result]] = OrderedDict()
        self._events: OrderedDict[str, EventEnvelope] = OrderedDict()
        self._errors: OrderedDict[str, EventEnvelope] = OrderedDict()
        self._parameters: dict[str, list[Parameter]] = {}
        # stream_id -> (component_ref, subscribe_id of its status events)
        self._streams: dict[str, tuple[str, str]] = {}

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
        sink: EventSink | None = None,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch a JSON-RPC method to the appropriate handler.

        Returns a result dict for the JSON-RPC response.
        """
        logger.debug("[engine] %s %s", method, json.dumps(params))
        if sink is not None:
            sink = self._recording(sink)

        if method == "rois.system.connect":
            return {"return_code": ReturnCode.OK.value}

        if method == "rois.system.disconnect":
            self.release_all(client_id or "")
            return {"return_code": ReturnCode.OK.value}

        if method == "rois.system.get_profile":
            return await self._handle_get_profile()

        if method == "rois.system.get_error_detail":
            return self._handle_get_error_detail(params)

        if method == "rois.command.search":
            return await self._handle_search()

        if method == "rois.command.bind":
            return self._handle_bind(params, client_id)

        if method == "rois.command.bind_any":
            return self._handle_bind_any(params, client_id)

        if method == "rois.command.release":
            return self._handle_release(params, client_id)

        if method == "rois.command.get_parameter":
            return await self._handle_get_parameter(params)

        if method == "rois.command.get_command_result":
            return self._handle_get_command_result(params)

        if method == "rois.command.execute":
            return await self._handle_execute(params, client_id, sink)

        if method == "rois.command.set_parameter":
            return await self._handle_set_parameter(params, client_id)

        if method == "rois.query.query":
            return await self._handle_query(params)

        if method == "rois.event.subscribe":
            return await self._handle_subscribe(params, sink)

        if method == "rois.event.unsubscribe":
            return await self._handle_unsubscribe(params)

        if method == "rois.event.get_event_detail":
            return self._handle_get_event_detail(params)

        if method == "rois.stream.connect_stream":
            return await self._handle_connect_stream(params, sink, client_id)

        if method in ("rois.stream.disconnect_stream", "rois.stream.suspend_stream",
                      "rois.stream.resume_stream"):
            return await self._handle_stream_command(method.rsplit(".", 1)[1], params, client_id)

        if method == "rois.stream.query_stream_status":
            return await self._handle_query_stream_status(params)

        return {"return_code": ReturnCode.UNSUPPORTED.value}

    # -- Streaming Interface: rois.stream.* onto the streaming component's messages --

    async def _handle_connect_stream(
        self,
        params: dict[str, Any],
        sink: EventSink | None,
        client_id: str | None,
    ) -> dict[str, Any]:
        """Ask a streaming component to open a stream, and route its status events back.

        The component answers with a stream_id and, in its results, whatever the
        transport needs to attach to the media (a URL, an SDP answer). Media never
        crosses the gateway.
        """
        component_ref = str(params.get("component_ref", ""))
        contract = self._contract_for(component_ref)
        if contract is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "stream_id": ""}
        response = await contract.invoke(CommandRequest(
            component_ref=component_ref,
            command_type=CommandType.CONNECT_STREAM,
            command_id=str(uuid.uuid4()),
            parameters=_to_parameters(params.get("parameters", [])),
        ))
        if response.return_code != ReturnCode.OK:
            return {"return_code": response.return_code.value, "stream_id": ""}
        stream_id = _result_value(response.results, "stream_id") or response.command_id
        subscribe_id = ""
        if sink is not None:
            subscribed = await contract.subscribe(SubscribeRequest(
                component_ref=component_ref, event_type=STREAM_STATUS,
            ), sink)
            subscribe_id = subscribed.subscribe_id
            contract.track_stream(stream_id, sink)  # type: ignore[attr-defined]
        self._streams[stream_id] = (component_ref, subscribe_id)
        return {
            "return_code": ReturnCode.OK.value,
            "stream_id": stream_id,
            "results": [r.model_dump() for r in response.results if r.name != "stream_id"],
        }

    async def _handle_stream_command(
        self,
        operation: str,
        params: dict[str, Any],
        client_id: str | None,
    ) -> dict[str, Any]:
        stream_id = str(params.get("stream_id", ""))
        entry = self._streams.get(stream_id)
        if entry is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value}
        component_ref, subscribe_id = entry
        contract = self._contract_for(component_ref)
        if contract is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value}
        response = await contract.invoke(CommandRequest(
            component_ref=component_ref,
            command_type=CommandType(operation),
            command_id=str(uuid.uuid4()),
            parameters=[Parameter(name="stream_id", data_type_ref="string", value=stream_id)],
        ))
        if operation == "disconnect_stream" and response.return_code == ReturnCode.OK:
            self._streams.pop(stream_id, None)
            if subscribe_id:
                await contract.unsubscribe(subscribe_id)
            contract.track_stream(stream_id, None)  # type: ignore[attr-defined]
        return {"return_code": response.return_code.value}

    async def _handle_query_stream_status(self, params: dict[str, Any]) -> dict[str, Any]:
        stream_id = str(params.get("stream_id", ""))
        entry = self._streams.get(stream_id)
        if entry is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "status": ""}
        contract = self._contract_for(entry[0])
        if contract is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "status": ""}
        # The profile's get_stream_status takes the stream_id as its argument; the
        # query condition carries it.
        response = await contract.query(QueryRequest(
            component_ref=entry[0], query_type="get_stream_status", condition=stream_id,
        ))
        return {
            "return_code": response.return_code.value,
            "status": _result_value(response.results, "status"),
        }

    def _recording(self, sink: EventSink) -> EventSink:
        """Wrap a sink so every delivered envelope stays available for the detail queries."""

        async def record_and_forward(envelope: EventEnvelope) -> None:
            if envelope.event_type == COMPLETED:
                command_id = _result_value(envelope.payload, "command_id")
                results = [r for r in envelope.payload if r.name != "command_id"]
                _remember(self._command_results, command_id, results)
            elif envelope.event_type == NOTIFY_ERROR:
                _remember(self._errors, envelope.event_id, envelope)
            else:
                _remember(self._events, envelope.event_id, envelope)
            await sink(envelope)

        return record_and_forward

    # -- Handlers --

    async def _handle_search(self) -> dict[str, Any]:
        """Return every component ref: local ones bare, child engine ones prefixed."""
        local = await self._component_registry.discover(DiscoverRequest())
        refs = list(local.component_ref_list)
        for entry in self._sub_engines.values():
            refs.extend(f"{entry['engine_id']}/{c['ref']}" for c in entry["components"])
        return {"return_code": ReturnCode.OK.value, "component_ref_list": refs}

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
                    "command_profiles": [
                        {"name": name, "results": []} for name in c.get("commands", [])
                    ],
                    "query_profiles": [
                        {"name": name, "results": []} for name in c.get("queries", [])
                    ],
                    "event_profiles": [
                        {"name": name, "results": []} for name in c.get("events", [])
                    ],
                    "parameter_profiles": [parameter_profile(p) for p in c.get("parameters", [])],
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
                "platform": self._platform,
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

    def _handle_bind_any(
        self,
        params: dict[str, Any],
        client_id: str | None,
    ) -> dict[str, Any]:
        """Bind the first free component whose ref matches the condition.

        RoIS leaves the condition language to the implementation. OpenRoIS
        matches it against the component refs, case-insensitively, so
        "Navigation" finds "robot_1/Navigation".
        """
        condition = str(params.get("condition", "")).lower()
        candidates = [
            ref for ref in self._all_refs() if condition in ref.lower()
        ]
        if not candidates:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "component_ref": ""}
        for ref in candidates:
            result = self._handle_bind({"component_ref": ref}, client_id)
            if result["return_code"] == ReturnCode.OK.value:
                return {"return_code": ReturnCode.OK.value, "component_ref": ref}
        return {"return_code": ReturnCode.OUT_OF_RESOURCES.value, "component_ref": ""}

    def _all_refs(self) -> list[str]:
        refs = list(self._component_registry.get_profile()["component_ids"])
        for entry in self._sub_engines.values():
            refs.extend(f"{entry['engine_id']}/{c['ref']}" for c in entry["components"])
        return refs

    def _handle_release(
        self,
        params: dict[str, Any],
        client_id: str | None,
    ) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        if self._bindings.get(component_ref) == (client_id or ""):
            self._bindings.pop(component_ref, None)
        return {"return_code": ReturnCode.OK.value}

    def _contract_for(self, component_ref: str) -> ComponentContract | None:
        """Pick the contract that owns a component ref: local first, then a child engine."""
        if self._component_registry.get_metadata(_bare_ref(component_ref)):
            return self._component_registry
        return self._find_sub_engine(component_ref)

    async def _handle_execute(
        self,
        params: dict[str, Any],
        client_id: str | None,
        sink: EventSink | None = None,
    ) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        component = self._find_component(component_ref)
        if not component:
            return {"return_code": ReturnCode.UNSUPPORTED.value}

        # Derive the binding requirement from function and commands.
        if isinstance(component, dict):
            function = component.get("function")
            commands = component.get("commands", [])
        else:
            function = component.function.value if component.function else None
            commands = list(component.invokes.keys()) if hasattr(component, "invokes") else []
        if _requires_bind(function, commands) and self._enforce_bindings:
            if self._bindings.get(component_ref) != (client_id or ""):
                return {"return_code": ReturnCode.OUT_OF_RESOURCES.value}

        # Accept the RoIS command_unit_list (first unit executed) and the flat
        # command_type + parameters shorthand.
        unit_list = params.get("command_unit_list", [])
        if isinstance(unit_list, list) and unit_list:
            unit = unit_list[0]
            command_type = str(unit.get("command_type", "execute"))
            raw = unit.get("arguments", [])
            command_id = str(unit.get("command_id", ""))
        else:
            command_type = str(params.get("command_type", "execute"))
            raw = params.get("parameters", params.get("arguments", []))
            command_id = str(params.get("command_id", ""))

        try:
            operation = CommandType(command_type)
        except ValueError:
            return {"return_code": ReturnCode.BAD_PARAMETER.value, "command_id": ""}
        contract = self._contract_for(component_ref)
        if contract is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value}
        request = CommandRequest(
            component_ref=component_ref,
            command_type=operation,
            command_id=command_id or str(uuid.uuid4()),
            parameters=_to_parameters(raw),
        )
        response = await contract.invoke(request)
        if response.return_code == ReturnCode.OK:
            if response.command_id:
                _remember(self._command_results, response.command_id, list(response.results))
                if sink is not None:
                    contract.track_command(response.command_id, sink)  # type: ignore[attr-defined]
        elif response.return_code == ReturnCode.ERROR and sink is not None:
            await sink(error_envelope(
                ErrorType.COMPONENT_INTERNAL_ERROR,
                f"{component_ref} failed to execute {command_type}",
                request.command_id,
            ))
        return response.model_dump(mode="json")

    async def _handle_set_parameter(
        self,
        params: dict[str, Any],
        client_id: str | None,
    ) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        contract = self._contract_for(component_ref)
        if contract is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value}
        parameters = _to_parameters(params.get("parameters", []))
        response = await contract.invoke(CommandRequest(
            component_ref=component_ref,
            command_type=CommandType.SET_PARAMETER,
            command_id=str(params.get("command_id", "")) or str(uuid.uuid4()),
            parameters=parameters,
        ))
        if response.return_code == ReturnCode.OK:
            self._parameters[component_ref] = parameters
        return response.model_dump(mode="json")

    async def _handle_get_parameter(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return a component's parameters.

        A component that declares a get_parameter query answers itself.
        Otherwise the engine returns what set_parameter last stored for it.
        """
        component_ref = str(params.get("component_ref", ""))
        names = [str(n) for n in params.get("names", [])]
        meta = self._component_registry.get_metadata(_bare_ref(component_ref))
        if meta is not None and "get_parameter" in meta.queries:
            response = await self._component_registry.query(QueryRequest(
                component_ref=component_ref, query_type="get_parameter",
            ))
            results = [r for r in response.results if not names or r.name in names]
            return {
                "return_code": response.return_code.value,
                "results": [r.model_dump() for r in results],
            }
        if self._find_component(component_ref) is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "results": []}
        stored = self._parameters.get(component_ref, [])
        return {
            "return_code": ReturnCode.OK.value,
            "results": [p.model_dump() for p in stored if not names or p.name in names],
        }

    def _handle_get_command_result(self, params: dict[str, Any]) -> dict[str, Any]:
        command_id = str(params.get("command_id", ""))
        results = self._command_results.get(command_id)
        if results is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "results": []}
        return {"return_code": ReturnCode.OK.value, "results": [r.model_dump() for r in results]}

    def _handle_get_error_detail(self, params: dict[str, Any]) -> dict[str, Any]:
        envelope = self._errors.get(str(params.get("error_id", "")))
        if envelope is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "results": []}
        return {
            "return_code": ReturnCode.OK.value,
            "error_id": envelope.event_id,
            "error_type": (envelope.error_type or ErrorType.ENGINE_INTERNAL_ERROR).value,
            "results": [r.model_dump() for r in envelope.payload],
        }

    def _handle_get_event_detail(self, params: dict[str, Any]) -> dict[str, Any]:
        envelope = self._events.get(str(params.get("event_id", "")))
        if envelope is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "results": []}
        return {"return_code": ReturnCode.OK.value, **envelope_to_params(envelope)}

    async def _handle_query(self, params: dict[str, Any]) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        contract = self._contract_for(component_ref)
        if contract is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "results": []}
        response = await contract.query(QueryRequest(
            component_ref=component_ref,
            query_type=str(params.get("query_type", "")),
            condition=str(params.get("condition", "")),
        ))
        return response.model_dump(mode="json")

    async def _handle_subscribe(
        self,
        params: dict[str, Any],
        sink: EventSink | None,
    ) -> dict[str, Any]:
        component_ref = str(params.get("component_ref", ""))
        if sink is None:
            logger.warning("[subscribe] no sink for %s, nowhere to deliver events", component_ref)
            return {"return_code": ReturnCode.ERROR.value, "subscribe_id": ""}
        contract = self._contract_for(component_ref)
        if contract is None:
            return {"return_code": ReturnCode.UNSUPPORTED.value, "subscribe_id": ""}
        response = await contract.subscribe(SubscribeRequest(
            component_ref=component_ref,
            event_type=str(params.get("event_type", "")),
            condition=str(params.get("condition", "")),
        ), sink)
        return response.model_dump(mode="json")

    async def _handle_unsubscribe(self, params: dict[str, Any]) -> dict[str, Any]:
        subscribe_id = str(params.get("subscribe_id", ""))
        if self._component_registry.owns_subscription(subscribe_id):
            code = await self._component_registry.unsubscribe(subscribe_id)
            return {"return_code": code.value}
        for entry in self._sub_engines.values():
            sub_engine: SubEngine = entry["sub_engine"]
            if sub_engine.owns_subscription(subscribe_id):
                code = await sub_engine.unsubscribe(subscribe_id)
                return {"return_code": code.value}
        # Unknown ids are already gone, which is what the caller wanted.
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
                sub_engine: SubEngine = entry["sub_engine"]
                return sub_engine
            return None

        owner = self._component_index.get(ref)
        if not owner:
            return None
        entry = self._sub_engines.get(owner)
        if not entry:
            return None
        found: SubEngine = entry["sub_engine"]
        return found
