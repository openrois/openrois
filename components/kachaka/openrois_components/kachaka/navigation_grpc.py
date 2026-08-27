"""Navigation component for the Kachaka robot (gRPC API).

Translates RoIS Navigation commands to Kachaka gRPC calls:
- execute: move_to_location() with the target location name.
- stop: cancel_command().
- component_status: poll get_command_state().
- reached_target event: poll command state and fire when completed.

The component owns its own state. It accesses the shared gRPC client
via self.parent._client, which the adapter creates in connect().
"""

from __future__ import annotations

import asyncio
import json
import logging

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import ReturnCode, Result
from openrois.sdk import component, invoke, query, results, subscribe

logger = logging.getLogger(__name__)


@component(
    "Navigation",
    bind_required=True,
    parameters=[
        {"name": "target_positions", "data_type_ref": "string[]",
         "description": "navigation target positions"},
        {"name": "time_limit", "data_type_ref": "int",
         "default_value": "0",
         "description": "intended time limit to complete navigation"},
        {"name": "routing_policy", "data_type_ref": "string",
         "default_value": "time",
         "description": "routing policy: 'time' priority or 'distance' priority"},
    ],
)
class GrpcNavigation:
    """Canonical RoIS Navigation component backed by Kachaka gRPC motion."""

    def __init__(self, config: dict) -> None:
        self._poll_interval = config.get("poll_interval", 0.5)
        self._nav_busy = False
        self._nav_target = ""
        self._time_limit = 0
        self._routing_policy = "time"
        self._locations_cache: list | None = None

    @query("get_parameter")
    async def get_parameter(self):
        """Return current parameter values: target_positions, time_limit, routing_policy."""
        target_positions = [self._nav_target] if self._nav_target else []
        return [
            Result(
                name="target_positions",
                data_type_ref="string[]",
                value=json.dumps(target_positions),
            ),
            Result(
                name="time_limit",
                data_type_ref="int",
                value=str(self._time_limit),
            ),
            Result(
                name="routing_policy",
                data_type_ref="string",
                value=self._routing_policy,
            ),
        ]

    @invoke("set_parameter")
    async def set_parameter(self, parameters):
        """Set navigation parameters before execute."""
        for p in parameters:
            name = p.get("name", "") if isinstance(p, dict) else getattr(p, "name", "")
            value = p.get("value", "") if isinstance(p, dict) else getattr(p, "value", "")
            if name == "target_positions":
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list) and parsed:
                        self._nav_target = parsed[0]
                    else:
                        self._nav_target = value
                except (json.JSONDecodeError, TypeError):
                    self._nav_target = value
            elif name == "time_limit":
                try:
                    self._time_limit = int(value)
                except ValueError:
                    pass
            elif name == "routing_policy":
                self._routing_policy = value
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @query("component_status")
    async def status(self):
        """Return READY when idle, BUSY when a command is running."""
        state, _ = await self.parent._client.get_command_state()
        if state == self.parent._pb2.CommandState.COMMAND_STATE_RUNNING:
            return results.status("BUSY")
        return results.status("READY")

    @invoke("execute")
    async def navigate(self, parameters):
        """Send a move_to_location command to the Kachaka robot.

        Uses the target set via set_parameter. If parameters are
        passed directly, parses target_positions from them by name.
        """
        if self._nav_busy:
            return InvokeResponse(
                return_code=ReturnCode.ERROR, command_id="",
            )
        # If parameters are passed, look for target_positions by name.
        # Otherwise, use the target set via set_parameter.
        target = self._nav_target
        if parameters:
            for p in parameters:
                name = p.get("name", "") if isinstance(p, dict) else getattr(p, "name", "")
                value = p.get("value", "") if isinstance(p, dict) else getattr(p, "value", "")
                if name == "target_positions" and value:
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, list) and parsed:
                            target = parsed[0]
                        else:
                            target = value
                    except (json.JSONDecodeError, TypeError):
                        target = value
                    break
        logger.info("navigate target=%s", target)
        if not target:
            return InvokeResponse(
                return_code=ReturnCode.BAD_PARAMETER, command_id="",
            )
        # Resolve location by name or ID.
        if not self._locations_cache:
            locations = await self.parent._client.get_locations()
            self._locations_cache = list(locations)
        loc = next(
            (l for l in self._locations_cache if l.name == target or l.id == target),
            None,
        )
        if loc is None:
            return InvokeResponse(
                return_code=ReturnCode.BAD_PARAMETER, command_id="",
            )
        await self.parent._client.move_to_location(
            loc.id, wait_for_completion=False,
        )
        self._nav_busy = True
        self._nav_target = target
        loop = asyncio.get_event_loop()
        loop.create_task(self._poll_reached())
        return InvokeResponse(
            return_code=ReturnCode.OK, command_id="cmd-nav",
        )

    @invoke("stop")
    async def stop(self, parameters):
        """Cancel the current motion command."""
        await self.parent._client.cancel_command()
        self._nav_busy = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("reached_target")
    async def on_reached(self):
        """Register the reached_target event subscription.

        The poll loop is started in navigate() after each command is
        issued. This handler exists so the framework registers the
        reached_target event subscription.
        """
        pass

    async def _poll_reached(self):
        """Poll get_command_state() until the command finishes."""
        was_running = False
        while True:
            await asyncio.sleep(self._poll_interval)
            state, _ = await self.parent._client.get_command_state()
            is_running = (
                state == self.parent._pb2.CommandState.COMMAND_STATE_RUNNING
            )
            if is_running:
                was_running = True
            elif was_running:
                self._nav_busy = False
                result, _ = (
                    await self.parent._client.get_last_command_result()
                )
                target_name = self._nav_target
                await self.parent.emit_async(
                    "Navigation",
                    "reached_target",
                    results.reached_target(
                        target=target_name, is_final_target=True,
                    ),
                )
                logger.info(
                    "Fired reached_target event (success=%s)", result.success,
                )
                return