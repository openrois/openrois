"""Person Detection component typed message models.

Derived from:
  - OMG RoIS Framework 2.0, RoIS_Person_Detection.idl
  - OMG RoIS Framework 2.0, PersonDetection.xml

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
from openrois.interfaces.components.rois_common import (
    ROIS_COMMON_PROFILE,
    ROIS_COMMON_URN,
    omg_identifier,
    parameter,
)
from openrois.interfaces.hri import DateTime, Integer
from openrois.interfaces.profiles import (
    ComponentFunction,
    EventMessageProfile,
    HRIComponentProfile,
)

# ---------------------------------------------------------------------------
# Component identifier
# ---------------------------------------------------------------------------

PERSON_DETECTION_URN = "urn:x-rois:def:component:OMG::PersonDetection"
"""Canonical URN for the PersonDetection component profile."""


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

PERSON_DETECTION_PROFILE = HRIComponentProfile(
    identifier=omg_identifier("PersonDetection"),
    name="person_detecter",
    function=ComponentFunction.SENSING,
    sub_component_profiles=[ROIS_COMMON_URN],
    command_profiles=[*ROIS_COMMON_PROFILE.command_profiles],
    query_profiles=[*ROIS_COMMON_PROFILE.query_profiles],
    event_profiles=[
        EventMessageProfile(
            name="person_detected",
            results=[
                parameter("number", "int", "number of detected persons"),
                parameter("timestamp", "DateTime", "time when measuered"),
            ],
        ),
    ],
)
"""The full PersonDetection profile.

PersonDetection.xml with the RoIS_Common messages it includes, and the RoSO function
``sensing``. The names and descriptions are those of the XML profile, word for word.
"""


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
