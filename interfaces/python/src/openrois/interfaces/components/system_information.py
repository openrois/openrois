"""System Information component typed message models.

Derived from:
  - OMG RoIS Framework 2.0, RoIS_System_Information.idl
  - OMG RoIS Framework 2.0, SystemInformation.xml

Component URN: urn:x-rois:def:component:OMG::SystemInformation

SystemInformation is unique among basic components: its XML profile includes no
RoIS_Common, so it has the robot_position and engine_status queries only. The IDL
derives its Query interface from RoIS_Common::Query, and the implementation follows
the XML profile (docs/rois-reference.md, section 16).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components.rois_common import omg_identifier, parameter
from openrois.interfaces.hri import DateTime, RoISIdentifierList
from openrois.interfaces.profiles import HRIComponentProfile, QueryMessageProfile

# ---------------------------------------------------------------------------
# Component identifier
# ---------------------------------------------------------------------------

SYSTEM_INFORMATION_URN = "urn:x-rois:def:component:OMG::SystemInformation"
"""Canonical URN for the SystemInformation component profile."""


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

SYSTEM_INFORMATION_PROFILE = HRIComponentProfile(
    identifier=omg_identifier("SystemInformation"),
    name="system_info",
    query_profiles=[
        QueryMessageProfile(
            name="robot_position",
            results=[
                parameter(
                    "position_data",
                    "String[]",
                    "position of robot or its parts in comma seperated double values [x, y, th]",
                ),
                parameter("robot_ref", "RoISIdentifier[]", "List of robot IDs"),
                parameter("timestamp", "DateTime", "timestamp of measurement"),
            ],
        ),
        QueryMessageProfile(
            name="engine_status",
            results=[
                parameter(
                    "operable_time",
                    "DateTime",
                    "Operable time of the HRI Engine that includes this basic component",
                ),
                parameter("status", "Component_Status", "Status information of this engine"),
            ],
        ),
    ],
)
"""The full SystemInformation profile, from SystemInformation.xml.

The ontology gives SystemInformation no RoSO function, so ``function`` is empty.
"""


# ---------------------------------------------------------------------------
# Query models
# ---------------------------------------------------------------------------


class SystemInformationRobotPositionResult(BaseModel):
    """Result payload for System_Information::Query::robot_position.

    Maps to the robot_position query in SystemInformation.xml.

    Attributes:
        timestamp: ISO 8601 datetime when the position was measured.
        robot_ref: List of robot identifiers in the position data.
        position_data: Positional/measurement data (RoLo Data sequence as strings).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    timestamp: DateTime = Field(description="Time when measured")
    robot_ref: RoISIdentifierList = Field(description="List of robot IDs")
    position_data: list[str] = Field(description="Position data (RoLo Data sequence)")


class SystemInformationEngineStatusResult(BaseModel):
    """Result payload for System_Information::Query::engine_status.

    Maps to the engine_status query in SystemInformation.xml.

    Attributes:
        status: Current component status of the engine.
        operable_time: List of ISO 8601 datetimes representing operable periods.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    status: ComponentStatus = Field(description="Engine component status")
    operable_time: list[DateTime] = Field(description="Operable time periods")
