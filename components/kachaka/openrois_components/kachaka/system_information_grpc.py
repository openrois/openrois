"""SystemInformation component for the Kachaka robot (gRPC API).

Status and location of the Kachaka robot via gRPC API. The component
owns its own gRPC client, created in connect() and torn down in
disconnect(). No dependency on the adapter for shared state.

robot_position is a poll-on-demand query. Each call fetches the
current pose from the robot via gRPC. No background polling.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from openrois_components_core import component, query, results

logger = logging.getLogger(__name__)


@component("SystemInformation")
class GrpcSystemInformation:
    """Status and location of the Kachaka robot via gRPC API."""

    def __init__(self, config: dict) -> None:
        self._engine_id = config.get("engine", {}).get("id", "robot_1")
        self._grpc_server = config.get(
            "grpc_server", "192.168.1.100:26400",
        )
        self._client = None
        self._connected = False
        self._init_time = datetime.now(timezone.utc).isoformat()

    async def connect(self) -> None:
        """Create the gRPC client and connect to the Kachaka robot."""
        from kachaka_api.aio import KachakaApiClient

        self._client = KachakaApiClient(target=self._grpc_server)
        await self._client.update_resolver()
        self._connected = True
        logger.info(
            "SystemInformation connected to Kachaka at %s",
            self._grpc_server,
        )

    async def disconnect(self) -> None:
        """Tear down the gRPC client."""
        self._connected = False
        self._client = None

    @query("robot_position")
    async def robot_position(self):
        if not self._connected or self._client is None:
            return results.robot_position(
                x=0.0, y=0.0, theta=0.0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                robot_ref=[self._engine_id],
            )
        pose = await self._client.get_robot_pose()
        timestamp = datetime.now(timezone.utc).isoformat()
        return results.robot_position(
            x=round(pose.x, 4), y=round(pose.y, 4), theta=round(pose.theta, 4),
            timestamp=timestamp, robot_ref=[self._engine_id],
        )

    @query("engine_status")
    async def engine_status(self):
        status = "READY" if self._connected else "ERROR"
        return results.engine_status(
            status=status, operable_time=[self._init_time],
        )

    @query("component_status")
    async def component_status(self):
        if not self._connected:
            return results.status("ERROR")
        return results.status("READY")