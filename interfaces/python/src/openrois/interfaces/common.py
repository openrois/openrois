"""Common component types derived from RoIS_Common.idl.

This module maps the OMG RoIS Framework 2.0 Common IDL types to Python Pydantic
models. These types define the base interfaces that every RoIS component inherits:
Command (start/stop/suspend/resume), Query (component_status), and Event.

Source: OMG RoIS Framework 2.0-beta2, RoIS_Common.idl
"""

from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ComponentStatus(StrEnum):
    """Status of a RoIS component.

    Maps to RoIS_Common::Component_Status in the IDL.

    UNINITIALIZED: Component has not been initialized.
    READY: Component is ready to operate.
    BUSY: Component is currently processing.
    WARNING: Component is operational but has a warning condition.
    ERROR: Component has encountered an error.
    """

    UNINITIALIZED = "UNINITIALIZED"
    READY = "READY"
    BUSY = "BUSY"
    WARNING = "WARNING"
    ERROR = "ERROR"


class StreamStatus(StrEnum):
    """Status of a streaming connection.

    Maps to RoIS_Common::Stream_Status in the IDL.

    NOT_CONNECTED: No peer connection established.
    NOT_RUNNING: Connection exists but stream is not active.
    RUNNING: Stream is actively delivering data.
    SUSPENDED: Stream has been suspended (track disabled).
    RESUMED: Stream has been resumed after suspension.
    """

    NOT_CONNECTED = "STREAMING_NOT_CONNECTED"
    NOT_RUNNING = "STREAMING_NOT_RUNNING"
    RUNNING = "STREAMING_RUNNING"
    SUSPENDED = "STREAMING_SUSPENDED"
    RESUMED = "STREAMING_RESUMED"


# ---------------------------------------------------------------------------
# Numeric type aliases
# ---------------------------------------------------------------------------

# RoIS_Common::Component_Status_t → long (numeric representation)
# Numeric representation of ComponentStatus for wire compatibility.
type ComponentStatusT = int

# RoIS_Common::Stream_Status_t → long (numeric representation)
# Numeric representation of StreamStatus for wire compatibility.
type StreamStatusT = int


# ---------------------------------------------------------------------------
# Convenience mappings
# ---------------------------------------------------------------------------

COMPONENT_STATUS_MAP: dict[ComponentStatus, ComponentStatusT] = {
    ComponentStatus.UNINITIALIZED: 0,
    ComponentStatus.READY: 1,
    ComponentStatus.BUSY: 2,
    ComponentStatus.WARNING: 3,
    ComponentStatus.ERROR: 4,
}
"""Mapping from ComponentStatus enum to numeric ComponentStatusT values."""

STREAM_STATUS_MAP: dict[StreamStatus, StreamStatusT] = {
    StreamStatus.NOT_CONNECTED: 0,
    StreamStatus.NOT_RUNNING: 1,
    StreamStatus.RUNNING: 2,
    StreamStatus.SUSPENDED: 3,
    StreamStatus.RESUMED: 4,
}
"""Mapping from StreamStatus enum to numeric StreamStatusT values."""
