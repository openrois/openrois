"""A SystemInformation component that reports a robot standing still at the origin.

SystemInformation.xml includes no RoIS_Common profile, so this component has the
robot_position and engine_status queries only, no commands and no component_status.
engine_status reports the status of the engine that hosts the component.
"""

from __future__ import annotations

from datetime import UTC, datetime

from openrois.components.core import Component, component, query
from openrois.interfaces.components import SYSTEM_INFORMATION_PROFILE


@component(SYSTEM_INFORMATION_PROFILE)
class MockSystemInformation(Component):
    """SystemInformation with a fixed position.

    Queries:
        robot_position: The robot at ``0.0,0.0,0.0``, identified by the engine id.
        engine_status: The status of the engine, operable since the component was
            created. It is READY unless WARNING or ERROR is raised on the engine.
    """

    def __init__(self) -> None:
        self._started = datetime.now(UTC)

    @query("robot_position")
    async def robot_position(self) -> dict[str, object]:
        """Report the robot at the origin of its map, measured now."""
        engine_id = self.ref.split("/", 1)[0]
        return {
            "position_data": ["0.0,0.0,0.0"],
            "robot_ref": [engine_id],
            "timestamp": datetime.now(UTC),
        }

    @query("engine_status")
    async def engine_status(self) -> dict[str, object]:
        """Report the status of the engine, operable since the component was created."""
        return {"operable_time": self._started, "status": self.engine_state()}
