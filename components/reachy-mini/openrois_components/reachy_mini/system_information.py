"""SystemInformation component for the Reachy Mini robot.

Provides robot position and engine status via the Reachy Python SDK.
The component accesses the Reachy client via self.parent._client.

The adapter must set _client before starting the framework. The Reachy
SDK client should be created in the adapter's connect() method so it
binds to the framework's event loop.

SystemInformation does not inherit RoIS_Common (no start/stop/suspend/
resume). It is a read-only status reporter.
"""

from __future__ import annotations

from openrois.interfaces.hri import Result
from openrois.sdk import component, query, results


@component("SystemInformation", bind_required=False)
class SystemInformation:
    """Status and location of the Reachy Mini robot.

    Queries:
        robot_position: x, y, theta from the robot's odometry or pose.
        engine_status: overall robot status (READY, BUSY, WARNING, ERROR).
    """

    @query("robot_position")
    async def robot_position(self):
        """Return the robot's current position from the Reachy SDK."""
        pose = await self.parent._client.get_odometry()
        return results.position(
            x=pose.x,
            y=pose.y,
            theta=pose.heading,
        )

    @query("engine_status")
    async def engine_status(self):
        """Return the robot's overall status."""
        # Check if the robot is connected and responsive.
        is_alive = self.parent._client.is_alive()
        if not is_alive:
            return [
                Result(
                    name="status",
                    data_type_ref="string",
                    value="ERROR",
                ),
            ]
        # Check battery level if available.
        battery = getattr(self.parent._client, "battery_level", None)
        if battery is not None and battery < 20:
            return [
                Result(
                    name="status",
                    data_type_ref="string",
                    value="WARNING",
                ),
            ]
        return [
            Result(
                name="status",
                data_type_ref="string",
                value="READY",
            ),
        ]