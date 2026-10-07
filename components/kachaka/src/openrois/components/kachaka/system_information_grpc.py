"""SystemInformation for the Kachaka, over its gRPC API.

``robot_position`` reads the pose of the Kachaka on each query. The component owns its
gRPC client, created in ``connect()``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from openrois.components.core import Component, component, query
from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components import SYSTEM_INFORMATION_PROFILE

logger = logging.getLogger(__name__)


@component(SYSTEM_INFORMATION_PROFILE)
class GrpcSystemInformation(Component):
    """SystemInformation backed by the Kachaka gRPC API.

    Args:
        grpc_server: The address of the Kachaka's gRPC API, for example
            ``192.168.1.100:26400``.
    """

    def __init__(self, grpc_server: str) -> None:
        self._grpc_server = grpc_server
        self._client: Any = None
        self._started = datetime.now(UTC)

    async def connect(self) -> None:
        from kachaka_api.aio import KachakaApiClient

        self._client = KachakaApiClient(target=self._grpc_server)
        await self._client.update_resolver()
        self._started = datetime.now(UTC)
        logger.info("SystemInformation connected to the Kachaka at %s", self._grpc_server)

    async def disconnect(self) -> None:
        self._client = None

    @query("robot_position")
    async def robot_position(self) -> dict[str, object]:
        """The pose of the Kachaka on its map, ``x,y,theta`` in meters and radians."""
        pose = await self._client.get_robot_pose()
        return {
            "position_data": [f"{pose.x:.4f},{pose.y:.4f},{pose.theta:.4f}"],
            "robot_ref": [self.ref.split("/", 1)[0]],
            "timestamp": datetime.now(UTC),
        }

    @query("engine_status")
    async def engine_status(self) -> dict[str, object]:
        """READY since the component connected.

        A component that could not connect answers no query, so READY is all it reports.
        """
        return {"operable_time": self._started, "status": ComponentStatus.READY}
