"""Service-side RoIS interfaces: the method catalog.

This module defines what a service application exchanges with an HRI Engine. It holds
one params model and one result model for every operation of SystemIF, CommandIF,
QueryIF and EventIF in RoIS_HRI.idl, the four interfaces as Protocols, and the method
table that binds each JSON-RPC method name to its models.

Mapping rules:
  - A params model has one field per IDL ``in`` parameter, with the IDL name.
  - A result model has ``return_code`` plus one field per IDL ``out`` parameter, with
    the IDL name. Out parameters default to empty values, because an engine that
    returns a failure code has nothing to put in them.
  - RoIS failures travel in ``return_code``. JSON-RPC errors are reserved for protocol
    faults, listed in JsonRpcErrorCode.

The Streaming interface (``rois.stream.*``) is not modelled. An engine answers those
methods with JsonRpcErrorCode.METHOD_NOT_FOUND.

Source: OMG RoIS Framework 2.0, RoIS_HRI.idl
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from openrois.interfaces.hri import (
    CommandId,
    CommandUnitSequenceItem,
    ConditionT,
    EventType,
    ParameterList,
    QueryType,
    ResultList,
    ReturnCode,
    RoISIdentifier,
    RoISIdentifierList,
    SubscribeId,
)
from openrois.interfaces.profiles import HRIEngineProfileType

# Prefix of the Streaming interface methods, which the catalog does not model.
STREAMING_METHOD_PREFIX = "rois.stream."


# ---------------------------------------------------------------------------
# JSON-RPC error codes
# ---------------------------------------------------------------------------


class JsonRpcErrorCode(IntEnum):
    """JSON-RPC 2.0 error codes an engine returns for protocol faults.

    A RoIS operation that runs and fails reports the failure in its ``return_code``.
    These codes cover requests that never reach a RoIS operation.

    PARSE_ERROR: The message is not valid JSON.
    INVALID_REQUEST: The message is not a valid JSON-RPC request.
    METHOD_NOT_FOUND: The method is not in the catalog, including every
        ``rois.stream.*`` method.
    INVALID_PARAMS: The params do not validate against the method's params model.
    INTERNAL_ERROR: The engine failed while handling the request.
    """

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


# ---------------------------------------------------------------------------
# SystemIF
# ---------------------------------------------------------------------------


class ConnectParams(BaseModel):
    """Params of rois.system.connect.

    Maps to SystemIF::connect(), which takes no arguments. A request may omit params.
    """

    model_config = {"frozen": True, "extra": "forbid"}


class ConnectResult(BaseModel):
    """Result of rois.system.connect.

    Maps to SystemIF::connect().

    Attributes:
        return_code: Outcome of the operation.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode


class DisconnectParams(BaseModel):
    """Params of rois.system.disconnect.

    Maps to SystemIF::disconnect(), which takes no arguments. A request may omit params.
    """

    model_config = {"frozen": True, "extra": "forbid"}


class DisconnectResult(BaseModel):
    """Result of rois.system.disconnect.

    Maps to SystemIF::disconnect().

    Attributes:
        return_code: Outcome of the operation.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode


class GetProfileParams(BaseModel):
    """Params of rois.system.get_profile.

    Maps to SystemIF::get_profile(in condition, out profile).

    Attributes:
        condition: Filter on the profile. Empty means no filter.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    condition: ConditionT = Field(default="", description="Filter on the profile")


class GetProfileResult(BaseModel):
    """Result of rois.system.get_profile.

    Maps to SystemIF::get_profile(in condition, out profile). The IDL carries the
    profile as an XML document in a string. OpenRoIS sends the structured form of
    the same XSD type.

    Attributes:
        return_code: Outcome of the operation.
        profile: The engine profile. Null when return_code is not OK.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode
    profile: HRIEngineProfileType | None = Field(default=None, description="The engine profile")


class GetErrorDetailParams(BaseModel):
    """Params of rois.system.get_error_detail.

    Maps to SystemIF::get_error_detail(in error_id, in condition, out results).

    Attributes:
        error_id: The error_id from a notify_error notification.
        condition: Filter on the results. Empty means no filter.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    error_id: str = Field(description="The error_id from a notify_error notification")
    condition: ConditionT = Field(default="", description="Filter on the results")


class GetErrorDetailResult(BaseModel):
    """Result of rois.system.get_error_detail.

    Maps to SystemIF::get_error_detail(in error_id, in condition, out results).

    Attributes:
        return_code: Outcome of the operation.
        results: Details of the error.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode
    results: ResultList = Field(default_factory=list, description="Details of the error")


# ---------------------------------------------------------------------------
# CommandIF
# ---------------------------------------------------------------------------


class SearchParams(BaseModel):
    """Params of rois.command.search.

    Maps to CommandIF::search(in condition, out component_ref_list).

    Attributes:
        condition: Filter on the components. Empty matches every component.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    condition: ConditionT = Field(default="", description="Filter on the components")


class SearchResult(BaseModel):
    """Result of rois.command.search.

    Maps to CommandIF::search(in condition, out component_ref_list).

    Attributes:
        return_code: Outcome of the operation.
        component_ref_list: Refs of the matching components.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode
    component_ref_list: RoISIdentifierList = Field(
        default_factory=list,
        description="Refs of the matching components",
    )


class BindParams(BaseModel):
    """Params of rois.command.bind.

    Maps to CommandIF::bind(in component_ref).

    Attributes:
        component_ref: The component to reserve for this client.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    component_ref: RoISIdentifier = Field(description="The component to reserve")


class BindResult(BaseModel):
    """Result of rois.command.bind.

    Maps to CommandIF::bind(in component_ref).

    Attributes:
        return_code: Outcome of the operation. OUT_OF_RESOURCES when another client
            holds the component.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode


class BindAnyParams(BaseModel):
    """Params of rois.command.bind_any.

    Maps to CommandIF::bind_any(in condition, out component_ref).

    Attributes:
        condition: Filter on the components the engine may choose from.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    condition: ConditionT = Field(
        default="",
        description="Filter on the components the engine may choose from",
    )


class BindAnyResult(BaseModel):
    """Result of rois.command.bind_any.

    Maps to CommandIF::bind_any(in condition, out component_ref).

    Attributes:
        return_code: Outcome of the operation.
        component_ref: The component the engine reserved. Empty when return_code is
            not OK.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode
    component_ref: RoISIdentifier = Field(default="", description="The component reserved")


class ReleaseParams(BaseModel):
    """Params of rois.command.release.

    Maps to CommandIF::release(in component_ref).

    Attributes:
        component_ref: The component to release.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    component_ref: RoISIdentifier = Field(description="The component to release")


class ReleaseResult(BaseModel):
    """Result of rois.command.release.

    Maps to CommandIF::release(in component_ref).

    Attributes:
        return_code: Outcome of the operation.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode


class GetParameterParams(BaseModel):
    """Params of rois.command.get_parameter.

    Maps to CommandIF::get_parameter(in component_ref, out parameters).

    Attributes:
        component_ref: The component whose parameters to read.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    component_ref: RoISIdentifier = Field(description="The component whose parameters to read")


class GetParameterResult(BaseModel):
    """Result of rois.command.get_parameter.

    Maps to CommandIF::get_parameter(in component_ref, out parameters).

    Attributes:
        return_code: Outcome of the operation.
        parameters: The current value of every parameter of the component.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode
    parameters: ParameterList = Field(
        default_factory=list,
        description="The current value of every parameter of the component",
    )


class SetParameterParams(BaseModel):
    """Params of rois.command.set_parameter.

    Maps to CommandIF::set_parameter(in component_ref, in parameters, out command_id).

    Attributes:
        component_ref: The component to configure.
        parameters: The parameters to set.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    component_ref: RoISIdentifier = Field(description="The component to configure")
    parameters: ParameterList = Field(description="The parameters to set")


class SetParameterResult(BaseModel):
    """Result of rois.command.set_parameter.

    Maps to CommandIF::set_parameter(in component_ref, in parameters, out command_id).
    The engine assigns the command_id. A completed notification reports the outcome.

    Attributes:
        return_code: Outcome of the request.
        command_id: Identifier of the parameter change, assigned by the engine.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode
    command_id: CommandId = Field(
        default="",
        description="Identifier of the parameter change, assigned by the engine",
    )


class ExecuteParams(BaseModel):
    """Params of rois.command.execute.

    Maps to CommandIF::execute(in command_unit_list). The application names every
    command with its own command_id, and completed notifications report each one.
    The engine rejects a command_id it already tracks with BAD_PARAMETER.

    Attributes:
        command_unit_list: Commands to run in order. A ConcurrentCommands item runs
            its commands at the same time.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    command_unit_list: list[CommandUnitSequenceItem] = Field(
        min_length=1,
        description="Commands to run in order",
    )


class ExecuteResult(BaseModel):
    """Result of rois.command.execute.

    Maps to CommandIF::execute(in command_unit_list), which has no out parameters.

    Attributes:
        return_code: Whether the engine accepted the commands. Completed
            notifications report how each command ended.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode


class GetCommandResultParams(BaseModel):
    """Params of rois.command.get_command_result.

    Maps to CommandIF::get_command_result(in command_id, in condition, out results).

    Attributes:
        command_id: The command whose results to read.
        condition: Filter on the results. Empty means no filter.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    command_id: CommandId = Field(description="The command whose results to read")
    condition: ConditionT = Field(default="", description="Filter on the results")


class GetCommandResultResult(BaseModel):
    """Result of rois.command.get_command_result.

    Maps to CommandIF::get_command_result(in command_id, in condition, out results).

    Attributes:
        return_code: Outcome of the operation.
        results: Results of the command.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode
    results: ResultList = Field(default_factory=list, description="Results of the command")


# ---------------------------------------------------------------------------
# QueryIF
# ---------------------------------------------------------------------------


class QueryParams(BaseModel):
    """Params of rois.query.query.

    Maps to QueryIF::query(in query_type, in condition, out results).

    Attributes:
        query_type: Name of the query, from a component profile.
        condition: Filter that selects the component and narrows the results.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    query_type: QueryType = Field(description="Name of the query, from a component profile")
    condition: ConditionT = Field(
        default="",
        description="Filter that selects the component and narrows the results",
    )


class QueryResult(BaseModel):
    """Result of rois.query.query.

    Maps to QueryIF::query(in query_type, in condition, out results).

    Attributes:
        return_code: Outcome of the operation.
        results: Results of the query.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode
    results: ResultList = Field(default_factory=list, description="Results of the query")


# ---------------------------------------------------------------------------
# EventIF
# ---------------------------------------------------------------------------


class SubscribeParams(BaseModel):
    """Params of rois.event.subscribe.

    Maps to EventIF::subscribe(in event_type, in condition, out subscribe_id).

    Attributes:
        event_type: Name of the event, from a component profile.
        condition: Filter that selects the component and narrows the events.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    event_type: EventType = Field(description="Name of the event, from a component profile")
    condition: ConditionT = Field(
        default="",
        description="Filter that selects the component and narrows the events",
    )


class SubscribeResult(BaseModel):
    """Result of rois.event.subscribe.

    Maps to EventIF::subscribe(in event_type, in condition, out subscribe_id).

    Attributes:
        return_code: Outcome of the operation.
        subscribe_id: Identifier of the subscription. Empty when return_code is not OK.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode
    subscribe_id: SubscribeId = Field(default="", description="Identifier of the subscription")


class UnsubscribeParams(BaseModel):
    """Params of rois.event.unsubscribe.

    Maps to EventIF::unsubscribe(in subscribe_id). Unsubscribing twice is not an error.

    Attributes:
        subscribe_id: The subscription to cancel.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    subscribe_id: SubscribeId = Field(description="The subscription to cancel")


class UnsubscribeResult(BaseModel):
    """Result of rois.event.unsubscribe.

    Maps to EventIF::unsubscribe(in subscribe_id).

    Attributes:
        return_code: Outcome of the operation.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode


class GetEventDetailParams(BaseModel):
    """Params of rois.event.get_event_detail.

    Maps to EventIF::get_event_detail(in event_id, in condition, out results).

    Attributes:
        event_id: The event_id from a notify_event notification.
        condition: Filter on the results. Empty means no filter.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    event_id: str = Field(description="The event_id from a notify_event notification")
    condition: ConditionT = Field(default="", description="Filter on the results")


class GetEventDetailResult(BaseModel):
    """Result of rois.event.get_event_detail.

    Maps to EventIF::get_event_detail(in event_id, in condition, out results).

    Attributes:
        return_code: Outcome of the operation.
        results: The event payload.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    return_code: ReturnCode
    results: ResultList = Field(default_factory=list, description="The event payload")


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------
#
# Each Protocol is the interface as one client session sees it. An engine serves every
# connected client through its own session object, which is how bind, execute and
# subscribe know which client is calling.


@runtime_checkable
class SystemIF(Protocol):
    """RoIS SystemIF, served to one client session."""

    async def connect(self, params: ConnectParams) -> ConnectResult:
        """Open the session. Maps to SystemIF::connect()."""
        ...

    async def disconnect(self, params: DisconnectParams) -> DisconnectResult:
        """Close the session and release its bindings. Maps to SystemIF::disconnect()."""
        ...

    async def get_profile(self, params: GetProfileParams) -> GetProfileResult:
        """Return the engine profile. Maps to SystemIF::get_profile()."""
        ...

    async def get_error_detail(self, params: GetErrorDetailParams) -> GetErrorDetailResult:
        """Return the details of a notified error. Maps to SystemIF::get_error_detail()."""
        ...


@runtime_checkable
class CommandIF(Protocol):
    """RoIS CommandIF, served to one client session."""

    async def search(self, params: SearchParams) -> SearchResult:
        """Find components. Maps to CommandIF::search()."""
        ...

    async def bind(self, params: BindParams) -> BindResult:
        """Reserve a component. Maps to CommandIF::bind()."""
        ...

    async def bind_any(self, params: BindAnyParams) -> BindAnyResult:
        """Reserve any matching free component. Maps to CommandIF::bind_any()."""
        ...

    async def release(self, params: ReleaseParams) -> ReleaseResult:
        """Release a reserved component. Maps to CommandIF::release()."""
        ...

    async def get_parameter(self, params: GetParameterParams) -> GetParameterResult:
        """Read the parameters of a component. Maps to CommandIF::get_parameter()."""
        ...

    async def set_parameter(self, params: SetParameterParams) -> SetParameterResult:
        """Change the parameters of a component. Maps to CommandIF::set_parameter()."""
        ...

    async def execute(self, params: ExecuteParams) -> ExecuteResult:
        """Run a sequence of commands. Maps to CommandIF::execute()."""
        ...

    async def get_command_result(self, params: GetCommandResultParams) -> GetCommandResultResult:
        """Return the results of a command. Maps to CommandIF::get_command_result()."""
        ...


@runtime_checkable
class QueryIF(Protocol):
    """RoIS QueryIF, served to one client session."""

    async def query(self, params: QueryParams) -> QueryResult:
        """Run a synchronous query. Maps to QueryIF::query()."""
        ...


@runtime_checkable
class EventIF(Protocol):
    """RoIS EventIF, served to one client session."""

    async def subscribe(self, params: SubscribeParams) -> SubscribeResult:
        """Subscribe to an event. Maps to EventIF::subscribe()."""
        ...

    async def unsubscribe(self, params: UnsubscribeParams) -> UnsubscribeResult:
        """Cancel a subscription. Maps to EventIF::unsubscribe()."""
        ...

    async def get_event_detail(self, params: GetEventDetailParams) -> GetEventDetailResult:
        """Return the payload of a notified event. Maps to EventIF::get_event_detail()."""
        ...


# ---------------------------------------------------------------------------
# Method table
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MethodSpec:
    """One entry of the method catalog.

    Attributes:
        method: The JSON-RPC method name.
        interface: The RoIS interface that defines the operation.
        operation: The operation name in the IDL, and the Protocol method name.
        params: The params model.
        result: The result model.
    """

    method: str
    interface: str
    operation: str
    params: type[BaseModel]
    result: type[BaseModel]


METHODS: tuple[MethodSpec, ...] = (
    MethodSpec("rois.system.connect", "SystemIF", "connect", ConnectParams, ConnectResult),
    MethodSpec(
        "rois.system.disconnect", "SystemIF", "disconnect", DisconnectParams, DisconnectResult
    ),
    MethodSpec(
        "rois.system.get_profile", "SystemIF", "get_profile", GetProfileParams, GetProfileResult
    ),
    MethodSpec(
        "rois.system.get_error_detail",
        "SystemIF",
        "get_error_detail",
        GetErrorDetailParams,
        GetErrorDetailResult,
    ),
    MethodSpec("rois.command.search", "CommandIF", "search", SearchParams, SearchResult),
    MethodSpec("rois.command.bind", "CommandIF", "bind", BindParams, BindResult),
    MethodSpec("rois.command.bind_any", "CommandIF", "bind_any", BindAnyParams, BindAnyResult),
    MethodSpec("rois.command.release", "CommandIF", "release", ReleaseParams, ReleaseResult),
    MethodSpec(
        "rois.command.get_parameter",
        "CommandIF",
        "get_parameter",
        GetParameterParams,
        GetParameterResult,
    ),
    MethodSpec(
        "rois.command.set_parameter",
        "CommandIF",
        "set_parameter",
        SetParameterParams,
        SetParameterResult,
    ),
    MethodSpec("rois.command.execute", "CommandIF", "execute", ExecuteParams, ExecuteResult),
    MethodSpec(
        "rois.command.get_command_result",
        "CommandIF",
        "get_command_result",
        GetCommandResultParams,
        GetCommandResultResult,
    ),
    MethodSpec("rois.query.query", "QueryIF", "query", QueryParams, QueryResult),
    MethodSpec("rois.event.subscribe", "EventIF", "subscribe", SubscribeParams, SubscribeResult),
    MethodSpec(
        "rois.event.unsubscribe", "EventIF", "unsubscribe", UnsubscribeParams, UnsubscribeResult
    ),
    MethodSpec(
        "rois.event.get_event_detail",
        "EventIF",
        "get_event_detail",
        GetEventDetailParams,
        GetEventDetailResult,
    ),
)

# The method table indexed by JSON-RPC method name, for request dispatch.
METHODS_BY_NAME: Mapping[str, MethodSpec] = MappingProxyType({m.method: m for m in METHODS})


def catalog_document() -> dict[str, object]:
    """Return the method table as the language-neutral document ``catalog.json``.

    The TypeScript and C# generators read this document to emit the method name
    constants and the method to model map, so every language shares one table.
    Models are named by their schema title.
    """
    return {
        "methods": [
            {
                "method": m.method,
                "interface": m.interface,
                "operation": m.operation,
                "params": m.params.__name__,
                "result": m.result.__name__,
            }
            for m in METHODS
        ],
        "json_rpc_error_codes": [{"name": c.name, "code": c.value} for c in JsonRpcErrorCode],
        "unmodelled_method_prefixes": [STREAMING_METHOD_PREFIX],
    }
