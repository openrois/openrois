"""Navigation component typed message models.

Derived from:
  - OMG RoIS Framework 2.0, RoIS_Navigation.idl
  - OMG RoIS Framework 2.0, Navigation.xml

Component URN: urn:x-rois:def:component:OMG::Navigation

This module demonstrates the full command + query + event pattern for a component
that has component-specific operations beyond the inherited RoIS_Common base.

The Navigation component inherits from RoIS_Common:
  - Command: start(), stop(), suspend(), resume(), set_parameter()
  - Query: component_status(), get_parameter()
  - Event: reached_target(target, is_final_target)
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components.rois_common import (
    ROIS_COMMON_PROFILE,
    ROIS_COMMON_URN,
    omg_identifier,
    parameter,
)
from openrois.interfaces.hri import (
    CommandId,
    Integer,
)
from openrois.interfaces.profiles import (
    ComponentFunction,
    EventMessageProfile,
    HRIComponentProfile,
)

# ---------------------------------------------------------------------------
# Component identifier
# ---------------------------------------------------------------------------

NAVIGATION_URN = "urn:x-rois:def:component:OMG::Navigation"
"""Canonical URN for the Navigation component profile."""


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

NAVIGATION_PROFILE = HRIComponentProfile(
    identifier=omg_identifier("Navigation"),
    name="navigation",
    function=ComponentFunction.ACTUATION,
    sub_component_profiles=[ROIS_COMMON_URN],
    command_profiles=[*ROIS_COMMON_PROFILE.command_profiles],
    query_profiles=[*ROIS_COMMON_PROFILE.query_profiles],
    event_profiles=[
        EventMessageProfile(
            name="reached_target",
            results=[
                parameter("target", "string", "reached target destination"),
                parameter("is_final_target", "bool", "if it is final destination point"),
            ],
        ),
    ],
    parameter_profiles=[
        parameter("target_positions", "string[]", "navigation target positions"),
        parameter("time_limit", "int", "intended time limit to complete navigation", "0"),
        parameter(
            "routing_policy",
            "string",
            "routing policy: 'time' priority or 'distance' priority",
            "time",
        ),
    ],
)
"""The full Navigation profile.

Navigation.xml with the RoIS_Common messages it includes, and the RoSO function
``actuation``. A component declares this profile and implements a part of it. The
engine serves the part the component implements.
"""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class RoutingPolicy(StrEnum):
    """Routing policy for Navigation.

    The XML profile defines routing_policy as a string with values 'time'
    or 'distance'. We constrain it to an enum for compile-time safety.
    """

    TIME = "time"
    DISTANCE = "distance"


# ---------------------------------------------------------------------------
# Command models
# ---------------------------------------------------------------------------


class NavigationSetParameter(BaseModel):
    """Command payload for Navigation::Command::set_parameter.

    Maps to the set_parameter operation in Navigation.xml.

    Attributes:
        target_positions: Navigation target positions as structured data.
            In the XML profile, data_type_ref is 'string[]'.
        time_limit: Intended time limit to complete navigation (default: 0).
        routing_policy: Routing policy: 'time' priority or 'distance' priority
            (default: 'time').
    """

    model_config = {"extra": "forbid"}

    target_positions: list[str] = Field(
        description="Navigation target positions",
    )
    time_limit: Integer = Field(
        default=0,
        description="Intended time limit to complete navigation",
    )
    routing_policy: RoutingPolicy = Field(
        default=RoutingPolicy.TIME,
        description="Routing policy: 'time' or 'distance' priority",
    )


class NavigationSetParameterResult(BaseModel):
    """Result of Navigation set_parameter command.

    Attributes:
        command_id: The assigned command identifier for this navigation command.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    command_id: CommandId


# ---------------------------------------------------------------------------
# Query models
# ---------------------------------------------------------------------------


class NavigationGetParameterResult(BaseModel):
    """Result payload for Navigation::Query::get_parameter.

    Maps to the get_parameter operation in Navigation.xml.

    Attributes:
        target_positions: Current navigation target positions.
        time_limit: Current time limit setting.
        routing_policy: Current routing policy setting.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    target_positions: list[str] = Field(
        description="Current navigation target positions",
    )
    time_limit: Integer = Field(
        description="Current time limit setting",
    )
    routing_policy: RoutingPolicy = Field(
        description="Current routing policy setting",
    )


class NavigationStatusResult(BaseModel):
    """Result model for Navigation component_status query.

    Attributes:
        status: Current status of the Navigation component.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    status: ComponentStatus


# ---------------------------------------------------------------------------
# Event models
# ---------------------------------------------------------------------------


class NavigationReachedTargetEvent(BaseModel):
    """Event payload for Navigation::Event::reached_target.

    Maps to the reached_target event in Navigation.xml.

    Attributes:
        target: The reached target destination.
        is_final_target: Whether this is the final destination point.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    target: str = Field(description="Reached target destination")
    is_final_target: bool = Field(description="Whether this is the final destination point")
