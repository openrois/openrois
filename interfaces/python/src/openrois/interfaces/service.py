"""Service application callback types derived from RoIS_Service.idl.

This module maps the OMG RoIS Framework 2.0 Service IDL types to Python Pydantic
models. These types define the callback interface (ServiceApplicationBase) that
the HRI Engine uses to notify service applications of errors, command completion,
and events.

Source: OMG RoIS Framework 2.0-beta2, RoIS_Service.idl
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from openrois.interfaces.hri import CommandId, DateTime, EventType, SubscribeId

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
# Callback event models — ServiceApplicationBase notifications
# ---------------------------------------------------------------------------


class NotifyErrorEvent(BaseModel):
    """Event payload for ServiceApplicationBase::notify_error.

    Attributes:
        error_id: Unique identifier for this error instance.
        error_type: Classification of the error.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    error_id: str
    error_type: ErrorType


class CompletedEvent(BaseModel):
    """Event payload for ServiceApplicationBase::completed.

    Attributes:
        command_id: The command identifier that completed.
        status: The completion status.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    command_id: CommandId
    status: CompletedStatus


class NotifyEventPayload(BaseModel):
    """Event payload for ServiceApplicationBase::notify_event.

    Attributes:
        event_id: Unique identifier for this event occurrence.
        event_type: The type of event (e.g., 'person_detected', 'face_localized').
        subscribe_id: The subscription identifier that this event matches.
        expire: ISO 8601 datetime when this event expires, or empty if no expiry.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    event_id: str
    event_type: EventType
    subscribe_id: SubscribeId
    expire: DateTime = ""
