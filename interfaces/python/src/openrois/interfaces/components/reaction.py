"""Reaction component typed message models.

Derived from:
  - normative/machine-readable/RoIS_Reaction.idl
  - normative/machine-readable/Reaction.xml

Component URN: urn:x-rois:def:component:OMG::Reaction

The Reaction component inherits from RoIS_Common:
  - Command: start(), stop(), suspend(), resume(), set_parameter()
  - Query: component_status(), get_parameter()
  - Event: (no component-specific events)

The Reaction component triggers expressive reactions on a host. On a physical
robot this maps to LED patterns or gestures. On a virtual avatar this maps to
animations or facial expressions. The interface is paradigm-neutral: the
``reaction_ref`` identifier is an opaque string whose meaning is defined by the
host backend, not by the type system.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.hri import CommandId, RoISIdentifier, RoISIdentifierList

# ---------------------------------------------------------------------------
# Component identifier
# ---------------------------------------------------------------------------

REACTION_URN = "urn:x-rois:def:component:OMG::Reaction"
"""Canonical URN for the Reaction component profile."""


# ---------------------------------------------------------------------------
# Command models
# ---------------------------------------------------------------------------


class ReactionSetParameter(BaseModel):
    """Command payload for Reaction::Command::set_parameter.

    Maps to the set_parameter operation in RoIS_Reaction.idl, which takes a
    ``RoIS_IdentifierList`` of reaction references. The XML profile declares
    ``reaction_ref`` as a single ``RoISIdentifier`` parameter, but the IDL
    operation signature accepts a list, so the model uses a list to match the
    operation contract.

    Attributes:
        reaction_ref: List of reaction identifiers to trigger. Each identifier
            is an opaque string whose meaning is defined by the host backend
            (e.g., "wave", "nod", "smile" for an avatar, or "led_green" for a
            robot).
    """

    model_config = {"extra": "forbid"}

    reaction_ref: RoISIdentifierList = Field(
        description="Reaction identifiers to trigger",
    )


class ReactionSetParameterResult(BaseModel):
    """Result of Reaction set_parameter command.

    Attributes:
        command_id: The assigned command identifier for this reaction command.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    command_id: CommandId


# ---------------------------------------------------------------------------
# Query models
# ---------------------------------------------------------------------------


class ReactionGetParameterResult(BaseModel):
    """Result payload for Reaction::Query::get_parameter.

    Maps to the get_parameter operation in RoIS_Reaction.idl, which returns the
    list of available reactions and the currently selected reaction reference.

    Attributes:
        available_reactions: List of reaction identifiers this host can perform.
        reaction_ref: Currently selected reaction identifier.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    available_reactions: RoISIdentifierList = Field(
        description="List of available reaction identifiers this host can perform",
    )
    reaction_ref: RoISIdentifier = Field(
        description="Currently selected reaction identifier",
    )


class ReactionStatusResult(BaseModel):
    """Result model for Reaction component_status query.

    Attributes:
        status: Current status of the Reaction component.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    status: ComponentStatus


# ---------------------------------------------------------------------------
# Event models
# ---------------------------------------------------------------------------

# Reaction has no component-specific events.
# It inherits the empty Event interface from RoIS_Common::Event.
