"""OpenRoIS Interfaces: Transport-independent RoIS type definitions.

This package contains Pydantic models derived from the OMG RoIS Framework
Version 2.0-beta2 IDL specification. They are the single source of truth for
all OpenRoIS types, exported to JSON Schema and generated into C# and
TypeScript.

Modules:
    hri:        Core HRI types (ReturnCode, Result, Parameter, Argument, etc.)
    common:     Common component types (ComponentStatus, StreamStatus)
    service:    Service application callback types (CompletedStatus, ErrorType)
    profiles:   Component profile schema models (from XML-Profiles.xsd)
    components: Per-component typed message models
"""

from openrois.interfaces.bus import (
    BusAdapterError,
    CommandRequest,
    ComponentContract,
    ComponentNotFoundError,
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
from openrois.interfaces.common import (
    ComponentStatus,
    ComponentStatusT,
    StreamStatus,
    StreamStatusT,
)
from openrois.interfaces.hri import (
    Argument,
    ArgumentList,
    CommandId,
    CommandType,
    CommandUnit,
    CommandUnitSequence,
    CommandUnitSequenceItem,
    ConcurrentCommands,
    ConditionT,
    DateTime,
    EventType,
    HRIEngineProfile,
    Integer,
    Parameter,
    ParameterList,
    QueryType,
    Result,
    ResultList,
    ReturnCode,
    RoISIdentifier,
    RoISIdentifierList,
    SubscribeId,
)
from openrois.interfaces.profiles import (
    CommandMessageProfile,
    EventMessageProfile,
    HRIComponentProfile,
    HRIEngineProfileType,
    MessageProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from openrois.interfaces.service import (
    CompletedEvent,
    CompletedStatus,
    ErrorType,
    NotifyErrorEvent,
    NotifyEventPayload,
)

__all__ = [
    # HRI core
    "Argument",
    "ArgumentList",
    "CommandUnit",
    "CommandUnitSequence",
    "CommandUnitSequenceItem",
    "ConcurrentCommands",
    "ConditionT",
    "DateTime",
    "HRIEngineProfile",
    "Integer",
    "Parameter",
    "ParameterList",
    "Result",
    "ResultList",
    "ReturnCode",
    "RoISIdentifier",
    "RoISIdentifierList",
    # Common
    "ComponentStatus",
    "ComponentStatusT",
    "StreamStatus",
    "StreamStatusT",
    # Profiles
    "CommandMessageProfile",
    "EventMessageProfile",
    "HRIComponentProfile",
    "HRIEngineProfileType",
    "MessageProfile",
    "ParameterProfile",
    "QueryMessageProfile",
    "RoISIdentifierType",
    # Service
    "CompletedEvent",
    "CompletedStatus",
    "ErrorType",
    "NotifyErrorEvent",
    "NotifyEventPayload",
    # Bus
    "BusAdapterError",
    "CommandId",
    "CommandRequest",
    "CommandType",
    "ComponentContract",
    "ComponentNotFoundError",
    "DiscoverRequest",
    "DiscoverResponse",
    "EventEnvelope",
    "EventSink",
    "EventType",
    "InvokeResponse",
    "QueryRequest",
    "QueryResponse",
    "QueryType",
    "SubscribeId",
    "SubscribeRequest",
    "SubscribeResponse",
]
