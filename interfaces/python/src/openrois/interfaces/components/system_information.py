"""System Information component typed message models.

Derived from:
  - OMG RoIS Framework 2.0-beta2, RoIS_System_Information.idl
  - OMG RoIS Framework 2.0-beta2, SystemInformation.xml

Component URN: urn:x-rois:def:component:OMG::SystemInformation

SystemInformation is unique among basic components: it does NOT inherit
from RoIS_Common (no start/stop/suspend/resume, no component_status).
It only has Query operations: robot_position and engine_status.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.hri import DateTime, RoISIdentifierList

# ---------------------------------------------------------------------------
# Component identifier
# ---------------------------------------------------------------------------

SYSTEM_INFORMATION_URN = "urn:x-rois:def:component:OMG::SystemInformation"
"""Canonical URN for the SystemInformation component profile."""


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
