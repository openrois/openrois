"""Navigation component for the Kachaka robot.

Translates RoIS Navigation commands to Kachaka gRPC calls:
- execute: move_to_location() with the target location name.
- stop: cancel_command().
- component_status: poll get_command_state().
- reached_target event: poll command state and fire when completed.

The component accesses the Kachaka API client via self.parent._client.
The adapter must set _client, _pb2, _nav_busy, _nav_target, and
_poll_interval before starting the framework.
"""

from __future__ import annotations

import asyncio
import json
import logging

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import ReturnCode, Result
from openrois.sdk import component, invoke, query, results, subscribe

logger = logging.getLogger(__name__)


@component("Navigation", bind_required=True)
class Navigation:
    """Canonical RoIS Navigation component backed by Kachaka motion."""

    @query("get_parameter")
    async def get_parameter(self):
        """Return target_positions (location names), time_limit, routing_policy."""
        locations = await self.parent._client.get_locations()
        self.parent._locations_cache = list(locations)
        target_positions = [loc.name for loc in locations]
        return [
            Result(
                name="target_positions",
                data_type_ref="string[]",
                value=json.dumps(target_positions),
            ),
            Result(
                name="time_limit",
                data_type_ref="int",
                value="0",
            ),
            Result(
                name="routing_policy",
                data_type_ref="string",
                value="time",
            ),
        ]

    @query("component_status")
    async def status(self):
        """Return READY when idle, BUSY when a command is running."""
        state, _ = await self.parent._client.get_command_state()
        if state == self.parent._pb2.CommandState.COMMAND_STATE_RUNNING:
            return results.status("BUSY")
        return results.status("READY")

    @invoke("execute")
    async def navigate(self, parameters):
        """Send a move_to_location command to the Kachaka robot."""
        if self.parent._nav_busy:
            return InvokeResponse(
                return_code=ReturnCode.ERROR, command_id="",
            )
        target = ""
        if parameters:
            p = parameters[0]
            raw_value = (
                p.get("value", "")
                if isinstance(p, dict)
                else getattr(p, "value", "")
            )
            try:
                parsed = json.loads(raw_value)
                if isinstance(parsed, list) and parsed:
                    target = parsed[0]
                else:
                    target = raw_value
            except (json.JSONDecodeError, TypeError):
                target = raw_value
        # Resolve location name to ID.
        if not self.parent._locations_cache:
            locations = await self.parent._client.get_locations()
            self.parent._locations_cache = list(locations)
        loc = next(
            (l for l in self.parent._locations_cache if l.name == target),
            None,
        )
        if loc is None:
            return InvokeResponse(
                return_code=ReturnCode.BAD_PARAMETER, command_id="",
            )
        await self.parent._client.move_to_location(
            loc.id, wait_for_completion=False,
        )
        self.parent._nav_busy = True
        self.parent._nav_target = target
        loop = asyncio.get_event_loop()
        loop.create_task(self._poll_reached())
        return InvokeResponse(
            return_code=ReturnCode.OK, command_id="cmd-nav",
        )

    @invoke("stop")
    async def stop(self, parameters):
        """Cancel the current motion command."""
        await self.parent._client.cancel_command()
        self.parent._nav_busy = False
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
            await asyncio.sleep(self.parent._poll_interval)
            state, _ = await self.parent._client.get_command_state()
            is_running = (
                state == self.parent._pb2.CommandState.COMMAND_STATE_RUNNING
            )
            if is_running:
                was_running = True
            elif was_running:
                self.parent._nav_busy = False
                result, _ = (
                    await self.parent._client.get_last_command_result()
                )
                target_name = getattr(self.parent, "_nav_target", "")
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