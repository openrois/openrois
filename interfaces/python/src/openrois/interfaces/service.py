"""Service application callback types derived from RoIS_Service.idl.

This module maps the OMG RoIS Framework 2.0 Service IDL types to Python Pydantic
models. These types define the callback interface (ServiceApplicationBase) that
the HRI Engine uses to notify service applications of errors, command completion,
and events.

Source: OMG RoIS Framework 2.0, RoIS_Service.idl
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from openrois.interfaces.hri import CommandId, DateTime, EventType, ResultList, SubscribeId

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CompletedStatus(StrEnum):
    """Status of a completed command execution.

    Maps to RoIS_Service::Completed_Status in the IDL.

    OK: Command completed successfully.
    ERROR: Command completed with an error.
    ABORT: Command was aborted.
    OUT_OF_RESOURCES: Command failed due to resource exhaustion.
    TIMEOUT: Command timed out before completion.
    """

    OK = "OK"
    ERROR = "ERROR"
    ABORT = "ABORT"
    OUT_OF_RESOURCES = "OUT_OF_RESOURCES"
    TIMEOUT = "TIMEOUT"


class ErrorType(StrEnum):
    """Classification of error notifications.

    Maps to RoIS_Service::ErrorType in the IDL.

    ENGINE_INTERNAL_ERROR: Error originating from the HRI Engine itself.
    COMPONENT_INTERNAL_ERROR: Error originating from a component.
    COMPONENT_NOT_RESPONDING: A component failed to respond within timeout.
    USER_DEFINED_ERROR: Application-specific error.
    """

    ENGINE_INTERNAL_ERROR = "ENGINE_INTERNAL_ERROR"
    COMPONENT_INTERNAL_ERROR = "COMPONENT_INTERNAL_ERROR"
    COMPONENT_NOT_RESPONDING = "COMPONENT_NOT_RESPONDING"
    USER_DEFINED_ERROR = "USER_DEFINED_ERROR"


# ---------------------------------------------------------------------------
# Notifications: ServiceApplicationBase operations
# ---------------------------------------------------------------------------
#
# The engine calls these operations on the service application as JSON-RPC
# notifications. The params model of each one is named after the IDL operation, like
# the request models of the catalog, and the method table lives in the catalog.


class NotifyErrorParams(BaseModel):
    """Params of the rois.system.notify_error notification.

    Maps to ServiceApplicationBase::notify_error(in error_id, in error_type). The
    details come from SystemIF::get_error_detail(error_id).

    Attributes:
        error_id: Identifier of this error, for get_error_detail.
        error_type: Classification of the error.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    error_id: str = Field(description="Identifier of this error, for get_error_detail")
    error_type: ErrorType


class CompletedParams(BaseModel):
    """Params of the rois.command.completed notification.

    Maps to ServiceApplicationBase::completed(in command_id, in status). The results
    come from CommandIF::get_command_result(command_id).

    Attributes:
        command_id: The command that ended, as the application named it.
        status: How the command ended.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    command_id: CommandId = Field(description="The command that ended")
    status: CompletedStatus


class NotifyEventParams(BaseModel):
    """Params of the rois.event.notify_event notification.

    Maps to ServiceApplicationBase::notify_event(in event_id, in event_type,
    in subscribe_id, in expire). The payload also comes from
    EventIF::get_event_detail(event_id) until the event expires.

    Attributes:
        event_id: Identifier of this event, for get_event_detail.
        event_type: The type of event (e.g., 'person_detected').
        subscribe_id: The subscription this event matches.
        expire: ISO 8601 datetime after which get_event_detail no longer has the
            event, or empty if it does not expire.
        results: The event payload. An OpenRoIS extension that saves one
            get_event_detail round trip per event.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    event_id: str = Field(description="Identifier of this event, for get_event_detail")
    event_type: EventType
    subscribe_id: SubscribeId
    expire: DateTime = ""
    results: ResultList = Field(
        default_factory=list,
        description="The event payload (OpenRoIS extension)",
    )


class ProfileChangedParams(BaseModel):
    """Params of the rois.system.profile_changed notification.

    Not part of RoIS: an OpenRoIS extension. The engine sends it when its profile
    changes, for example when a child engine connects or disconnects, so a client
    calls get_profile again instead of polling it. It carries no params.
    """

    model_config = {"frozen": True, "extra": "forbid"}
