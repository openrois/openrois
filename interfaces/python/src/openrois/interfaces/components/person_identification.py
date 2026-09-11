"""Person Identification component typed message models.

Derived from:
  - OMG RoIS Framework 2.0-beta2, RoIS_Person_Identification.idl
  - OMG RoIS Framework 2.0-beta2, PersonIdentification.xml

Component URN: urn:x-rois:def:component:OMG::PersonIdentification

The Person Identification component inherits from RoIS_Common:
  - Command: start(), stop(), suspend(), resume()  (no component-specific commands)
  - Query: component_status()  (no component-specific queries)
  - Event: person_identified(timestamp, number, identifiers)

Identifier semantics:
  The identifiers published by this component are session-scoped
  tracking IDs, NOT persistent personal identities. They are reset
  when the perception pipeline restarts and may switch under occlusion
  or person crossing. Service applications must not treat them as
  stable across sessions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.hri import DateTime, Integer

# ---------------------------------------------------------------------------
# Component identifier
# ---------------------------------------------------------------------------

PERSON_IDENTIFICATION_URN = "urn:x-rois:def:component:OMG::PersonIdentification"
"""Canonical URN for the PersonIdentification component profile."""


# ---------------------------------------------------------------------------
# Event models
# ---------------------------------------------------------------------------


class PersonIdentifier(BaseModel):
    """Identifier assigned to a single identified person.

    Attributes:
        id: Session-scoped tracking identifier. Not a persistent
            personal identifier: it is reset when the perception
            pipeline restarts and may switch under occlusion.
        name: Optional human-readable name, empty when unknown.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    id: str = Field(description="Session-scoped tracking ID (not persistent)")
    name: str = Field(default="", description="Human-readable name, empty if unknown")


class PersonIdentifiedEvent(BaseModel):
    """Event payload for Person_Identification::Event::person_identified.

    Attributes:
        timestamp: ISO 8601 datetime when the identification was measured.
        number: Number of identified persons in this observation.
        identifiers: Identifier assigned to each identified person.
            These are session-scoped tracking IDs, not persistent
            personal identities.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    timestamp: DateTime = Field(description="Time when measured")
    number: Integer = Field(description="Number of identified persons")
    identifiers: list[PersonIdentifier] = Field(
        description="Session-scoped identifiers of identified persons",
    )


# ---------------------------------------------------------------------------
# Command models (inherited from RoIS_Common — no component-specific commands)
# ---------------------------------------------------------------------------

# PersonIdentification has no component-specific set_parameter.
# It inherits: start(), stop(), suspend(), resume() from RoIS_Common::Command.


# ---------------------------------------------------------------------------
# Query models (inherited from RoIS_Common — no component-specific queries)
# ---------------------------------------------------------------------------

# PersonIdentification has no component-specific queries.
# It inherits: component_status() from RoIS_Common::Query.


class PersonIdentificationStatusResult(BaseModel):
    """Result model for PersonIdentification component_status query.

    Attributes:
        status: Current status of the PersonIdentification component.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    status: ComponentStatus