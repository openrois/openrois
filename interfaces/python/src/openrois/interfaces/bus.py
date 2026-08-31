"""Transport-neutral component contract for OpenRoIS.

This module defines the ComponentContract protocol — the only boundary the RoIS
engine and gateway depend on. Every concrete bus (in-process, ROS 2, gRPC,
WebSocket, etc.) implements this five-method contract:

    discover  -> CommandIF.search
    invoke    -> CommandIF.bind/set_parameter/execute/start/stop/suspend/resume
    query     -> QueryIF.query / RoIS_Common.component_status
    subscribe -> EventIF.subscribe (async push via EventSink)
    unsubscribe -> EventIF.unsubscribe

The contract is intentionally transport-agnostic. No ROS, DDS, gRPC, WebSocket,
or socket symbols appear here.

Source: roadmap.md M0 Task 0.2
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from openrois.interfaces.common import ComponentStatus, StreamStatus
from openrois.interfaces.hri import (
    ArgumentList,
    CommandId,
    CommandType,
    CommandUnitSequence,
    ConditionT,
    DateTime,
    EventType,
    ParameterList,
    QueryType,
    ResultList,
    ReturnCode,
    RoISIdentifier,
    RoISIdentifierList,
    SubscribeId,
)
from openrois.interfaces.service import CompletedStatus, ErrorType

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Async callback that receives event envelopes from a ComponentContract.
# The sink is invoked by the adapter whenever an event matching a subscription
# occurs. The engine or gateway layer dispatches the generic envelope to typed
# handlers (notify_event, notify_error, completed, notify_stream_status).
type EventSink = Callable[[EventEnvelope], Awaitable[None]]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BusAdapterError(Exception):
    """Base exception raised by ComponentContract implementations."""

    def __init__(self, message: str, return_code: ReturnCode = ReturnCode.ERROR) -> None:
        super().__init__(message)
        self.message = message
        self.return_code = return_code


class ComponentNotFoundError(BusAdapterError):
    """Raised when a component_ref cannot be resolved by the adapter."""

    def __init__(self, component_ref: RoISIdentifier) -> None:
        super().__init__(
            f"Component not found: {component_ref}",
            return_code=ReturnCode.UNSUPPORTED,
        )
        self.component_ref = component_ref


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class DiscoverRequest(BaseModel):
    """Request to discover components matching a condition.

    Maps to CommandIF.search(condition, component_ref_list).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    condition: ConditionT = Field(
        default="",
        description="ISO 19143 filter expression; empty means all components",
    )


class DiscoverResponse(BaseModel):
    """Response from discover() carrying matching component references."""

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode = ReturnCode.OK
    component_ref_list: RoISIdentifierList = Field(default_factory=list)


class CommandRequest(BaseModel):
    """Generic command request sent via ComponentContract.invoke().

    Carries the same information as a CommandUnit plus the target component_ref.
    Typed component models (e.g., NavigationSetParameter) serialize their fields
    into arguments/parameters and are wrapped in this generic container.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    component_ref: RoISIdentifier = Field(description="Target component instance ref")
    command_type: CommandType = Field(
        description="Command operation: start, stop, suspend, resume, set_parameter, execute",
    )
    command_id: CommandId = Field(description="Unique command instance identifier")
    arguments: ArgumentList = Field(default_factory=list)
    parameters: ParameterList = Field(
        default_factory=list,
        description="Named parameter values for set_parameter-style commands",
    )
    command_unit_sequence: CommandUnitSequence | None = Field(
        default=None,
        description="Structured command sequence for execute()",
    )


class InvokeResponse(BaseModel):
    """Response from ComponentContract.invoke()."""

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode = ReturnCode.OK
    command_id: CommandId = Field(
        default="",
        description="Identifier for the invoked command; empty for synchronous ops",
    )
    results: ResultList = Field(
        default_factory=list,
        description="Immediate results, if any; typed by component profile",
    )


class QueryRequest(BaseModel):
    """Generic query request sent via ComponentContract.query().

    Maps to QueryIF.query(query_type, condition, results) and
    RoIS_Common.component_status(status).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    component_ref: RoISIdentifier = Field(description="Target component instance ref")
    query_type: QueryType = Field(description="Query operation name")
    condition: ConditionT = Field(
        default="",
        description="Optional filter expression for the query",
    )


class QueryResponse(BaseModel):
    """Response from ComponentContract.query()."""

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode = ReturnCode.OK
    results: ResultList = Field(
        default_factory=list,
        description="Query results; typed by component profile",
    )


class SubscribeRequest(BaseModel):
    """Request to subscribe to events matching a condition.

    Maps to EventIF.subscribe(event_type, condition, subscribe_id).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    component_ref: RoISIdentifier = Field(description="Target component instance ref")
    event_type: EventType = Field(description="Event type to subscribe to")
    condition: ConditionT = Field(
        default="",
        description="Optional filter expression for the subscription",
    )


class SubscribeResponse(BaseModel):
    """Response from ComponentContract.subscribe()."""

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode = ReturnCode.OK
    subscribe_id: SubscribeId = Field(
        default="",
        description="Identifier for the active subscription",
    )


# ---------------------------------------------------------------------------
# Event envelope
# ---------------------------------------------------------------------------


class EventEnvelope(BaseModel):
    """Generic event envelope delivered to an EventSink.

    The ComponentContract emits this for every async notification: component events,
    command completion, errors, and stream status changes. The engine/gateway
    inspects event_type and dispatches to the appropriate ServiceApplicationBase
    callback.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    event_id: str = Field(description="Unique identifier for this event occurrence")
    event_type: EventType = Field(
        description="Event type, e.g. person_detected, completed, notify_error",
    )
    subscribe_id: SubscribeId = Field(
        default="",
        description="Subscription identifier this event matches, if any",
    )
    component_ref: RoISIdentifier = Field(
        default="",
        description="Component ref that emitted the event, if any",
    )
    expire: DateTime = Field(
        default="",
        description="ISO 8601 datetime when this event expires",
    )
    payload: ResultList = Field(
        default_factory=list,
        description="Event payload as generic results; typed by component profile",
    )

    # Service-level metadata (populated by the engine when event_type matches)
    error_type: ErrorType | None = Field(
        default=None,
        description="Error classification when event_type is notify_error",
    )
    completed_status: CompletedStatus | None = Field(
        default=None,
        description="Completion status when event_type is completed",
    )
    stream_status: StreamStatus | None = Field(
        default=None,
        description="Stream status when event_type is notify_stream_status",
    )
    component_status: ComponentStatus | None = Field(
        default=None,
        description="Component status when event_type is component_status",
    )


# ---------------------------------------------------------------------------
# ComponentContract protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ComponentContract(Protocol):
    """Transport-neutral contract between the RoIS engine and a concrete bus.

    Implementations include:
      - SubEngine (remote adapter via WebSocket JSON-RPC)
      - ComponentRegistry (local components in-process)
      - UniversalBusAdapter  (M1, WS+JSON-RPC for non-ROS hosts)
      - ROS2BusAdapter        (M3)
      - RosBridgeBusAdapter   (future)

    The contract is intentionally limited to five async methods. Adapters must
    not leak transport-specific types through these signatures.
    """

    async def discover(self, request: DiscoverRequest) -> DiscoverResponse:
        """Discover components matching the request condition.

        Maps to CommandIF.search().
        """
        ...

    async def invoke(self, request: CommandRequest) -> InvokeResponse:
        """Invoke a command on a bound component.

        Maps to CommandIF operations: bind, set_parameter, execute,
        start/stop/suspend/resume.
        """
        ...

    async def query(self, request: QueryRequest) -> QueryResponse:
        """Execute a synchronous query on a component.

        Maps to QueryIF.query() and RoIS_Common.component_status().
        """
        ...

    async def subscribe(
        self,
        request: SubscribeRequest,
        sink: EventSink,
    ) -> SubscribeResponse:
        """Subscribe to async events from a component.

        Maps to EventIF.subscribe(). The adapter calls ``sink`` for each
        matching event until unsubscribe() is called.
        """
        ...

    async def unsubscribe(self, subscribe_id: SubscribeId) -> ReturnCode:
        """Cancel an event subscription.

        Maps to EventIF.unsubscribe(subscribe_id). Duplicate unsubscribe
        requests for the same subscribe_id are silently ignored (no error).
        """
        ...
