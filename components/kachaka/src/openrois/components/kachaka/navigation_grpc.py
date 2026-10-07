"""Navigation for the Kachaka, over its gRPC API.

``start`` drives to the first of ``target_positions``, a location of the Kachaka named by
its name or its id, and runs until the robot gets there. ``stop`` cancels the drive.
The component owns its gRPC client, created in ``connect()``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from openrois.components.core import CommandFailed, Component, component, invoke, subscribe
from openrois.interfaces.components import NAVIGATION_PROFILE
from openrois.interfaces.service import CompletedStatus

logger = logging.getLogger(__name__)


@component(NAVIGATION_PROFILE)
class GrpcNavigation(Component):
    """Navigation backed by the Kachaka gRPC API.

    Args:
        grpc_server: The address of the Kachaka's gRPC API, for example
            ``192.168.1.100:26400``.
        auto_homing: Whether the Kachaka returns to its charger when it is idle.
    """

    def __init__(self, grpc_server: str, *, auto_homing: bool = False) -> None:
        self._grpc_server = grpc_server
        self._auto_homing = auto_homing
        self._client: Any = None

    async def connect(self) -> None:
        from kachaka_api.aio import KachakaApiClient

        self._client = KachakaApiClient(target=self._grpc_server)
        await self._client.update_resolver()
        await self._client.set_auto_homing_enabled(self._auto_homing)
        logger.info("Navigation connected to the Kachaka at %s", self._grpc_server)

    async def disconnect(self) -> None:
        self._client = None

    @invoke("start")
    async def start(self) -> None:
        targets = self.parameters.get("target_positions", [])
        if not targets:
            raise CommandFailed(CompletedStatus.ERROR, "target_positions is empty")
        target = targets[0]
        location_id = await self._location_id(target)
        logger.info("Driving to %s", target)
        # The call returns when the drive ends. A stop, or a new start, halts the robot
        # with the stop handler first and then cancels this task, which ends with ABORT.
        try:
            result = await self._client.move_to_location(location_id, wait_for_completion=True)
        except asyncio.CancelledError:
            # When the engine shuts down, nothing else halts the robot.
            with contextlib.suppress(Exception):
                await self._client.cancel_command()
            raise
        if not result.success:
            raise CommandFailed(
                CompletedStatus.ERROR, f"The drive to {target} failed: {result.error_code}"
            )
        self.emit("reached_target", target=target, is_final_target=True)

    @invoke("stop")
    async def stop(self) -> None:
        await self._client.cancel_command()

    @subscribe("reached_target")
    async def reached_target(self) -> None:
        pass  # start emits the event when the drive ends.

    async def _location_id(self, target: str) -> str:
        """The id of the location a target names, by its name or its id."""
        for location in await self._client.get_locations():
            if target in (location.name, location.id):
                location_id: str = location.id
                return location_id
        raise CommandFailed(CompletedStatus.ERROR, f"The Kachaka knows no location {target!r}")
