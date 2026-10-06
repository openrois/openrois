"""Person Localization component typed message models.

Derived from:
  - OMG RoIS Framework 2.0-beta2, RoIS_Person_Localization.idl
  - OMG RoIS Framework 2.0-beta2, PersonLocalization.xml

Component URN: urn:x-rois:def:component:OMG::PersonLocalization

The Person Localization component inherits from RoIS_Common:
  - Command: start(), stop(), suspend(), resume()  (no component-specific commands)
  - Query: component_status()  (no component-specific queries)
  - Event: person_localized(timestamp, number, positions)

Coordinate frame convention:
  Positions are expressed in the robot body frame (REP-103): +x forward,
  +y left, +z up, in meters. Adapters converting from camera optical
  frames (+x right, +y down, +z forward) must apply the appropriate
  transform before publishing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.hri import DateTime, Integer

# ---------------------------------------------------------------------------
# Component identifier
# ---------------------------------------------------------------------------

PERSON_LOCALIZATION_URN = "urn:x-rois:def:component:OMG::PersonLocalization"
"""Canonical URN for the PersonLocalization component profile."""


# ---------------------------------------------------------------------------
# Event models
# ---------------------------------------------------------------------------


class PersonPosition(BaseModel):
    """3D position of a single localized person.

    Attributes:
        id: Session-scoped tracking identifier of the person. Not a
            persistent personal identifier: it is reset when the
            perception pipeline restarts and may switch under
            occlusion.
        x: X coordinate [m] in the robot body frame (+x forward).
        y: Y coordinate [m] in the robot body frame (+y left).
        z: Z coordinate [m] in the robot body frame (+z up).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    id: str = Field(description="Session-scoped tracking ID of the person")
    x: float = Field(description="X coordinate [m], robot body frame (+x forward)")
    y: float = Field(description="Y coordinate [m], robot body frame (+y left)")
    z: float = Field(description="Z coordinate [m], robot body frame (+z up)")


class PersonLocalizedEvent(BaseModel):
    """Event payload for Person_Localization::Event::person_localized.

    Attributes:
        timestamp: ISO 8601 datetime when the positions were measured.
        number: Number of localized persons in this observation.
        positions: 3D position of each localized person, in the robot
            body frame (REP-103: +x forward, +y left, +z up), meters.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    timestamp: DateTime = Field(description="Time when measured")
    number: Integer = Field(description="Number of localized persons")
    positions: list[PersonPosition] = Field(
        description="3D positions of localized persons (robot body frame, meters)",
    )


# ---------------------------------------------------------------------------
# Command models (inherited from RoIS_Common — no component-specific commands)
# ---------------------------------------------------------------------------

# PersonLocalization has no component-specific set_parameter.
# It inherits: start(), stop(), suspend(), resume() from RoIS_Common::Command.


# ---------------------------------------------------------------------------
# Query models (inherited from RoIS_Common — no component-specific queries)
# ---------------------------------------------------------------------------

# PersonLocalization has no component-specific queries.
# It inherits: component_status() from RoIS_Common::Query.


class PersonLocalizationStatusResult(BaseModel):
    """Result model for PersonLocalization component_status query.

    Attributes:
        status: Current status of the PersonLocalization component.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    status: ComponentStatus