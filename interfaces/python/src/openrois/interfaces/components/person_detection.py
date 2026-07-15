"""Person Detection component typed message models.

Derived from:
  - OMG RoIS Framework 2.0-beta2, RoIS_Person_Detection.idl
  - OMG RoIS Framework 2.0-beta2, PersonDetection.xml

Component URN: urn:x-rois:def:component:OMG::PersonDetection

This module demonstrates the "typed message per component" pattern: instead of
using the generic `Result(value=str)` for event payloads, we define a typed
Pydantic model that provides compile-time safety and clear field documentation.

The Person Detection component inherits from RoIS_Common:
  - Command: start(), stop(), suspend(), resume()  (no component-specific commands)
  - Query: component_status()  (no component-specific queries)
  - Event: person_detected(timestamp, number)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.hri import DateTime, Integer

# ---------------------------------------------------------------------------
# Component identifier
# ---------------------------------------------------------------------------

PERSON_DETECTION_URN = "urn:x-rois:def:component:OMG::PersonDetection"
"""Canonical URN for the PersonDetection component profile."""


# ---------------------------------------------------------------------------
# Event models
# ---------------------------------------------------------------------------


class PersonDetectedEvent(BaseModel):
    """Event payload for Person_Detection::Event::person_detected.

    Maps to the person_detected event in PersonDetection.xml.

    Attributes:
        timestamp: ISO 8601 datetime when the detection was measured.
        number: Number of detected persons in the current frame/observation.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    timestamp: DateTime = Field(description="Time when measured")
    number: Integer = Field(description="Number of detected persons")


# ---------------------------------------------------------------------------
# Command models (inherited from RoIS_Common — no component-specific commands)
# ---------------------------------------------------------------------------

# PersonDetection has no component-specific set_parameter.
# It inherits: start(), stop(), suspend(), resume() from RoIS_Common::Command.


# ---------------------------------------------------------------------------
# Query models (inherited from RoIS_Common — no component-specific queries)
# ---------------------------------------------------------------------------

# PersonDetection has no component-specific queries.
# It inherits: component_status() from RoIS_Common::Query.


class PersonDetectionStatusResult(BaseModel):
    """Result model for PersonDetection component_status query.

    Attributes:
        status: Current status of the PersonDetection component.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    status: ComponentStatus
