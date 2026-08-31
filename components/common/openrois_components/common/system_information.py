"""Mock SystemInformation component for testing and development.

Returns hardcoded position and status values. Useful for adapters that
need a SystemInformation component during development but do not yet
have a real robot connection. Also serves as a template for
platform-specific SystemInformation implementations.

SystemInformation does not inherit RoIS_Common::Command (no start/stop/
suspend/resume). It inherits RoIS_Common::Query (component_status) and
adds robot_position and engine_status. It is a read-only status reporter
per the RoIS specification.
"""

from __future__ import annotations

from openrois.interfaces.hri import Result
from openrois_components_core import component, query, results


@component("SystemInformation")
class MockSystemInformation:
    """Mock SystemInformation returning fixed position and status.

    Queries:
        robot_position: hardcoded x=0.0, y=0.0, theta=0.0.
        engine_status: always READY.
    """

    @query("robot_position")
    async def robot_position(self):
        """Return a fixed origin position."""
        return results.position(x=0.0, y=0.0, theta=0.0)

    @query("engine_status")
    async def engine_status(self):
        """Return READY status."""
        return [
            Result(
                name="status",
                data_type_ref="string",
                value="READY",
            ),
        ]