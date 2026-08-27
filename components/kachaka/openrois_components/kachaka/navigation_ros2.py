"""Navigation component for the Kachaka robot (ROS 2).

Translates RoIS Navigation commands to Kachaka ROS 2 action calls:
- execute: send_move_to_location() with the target location ID.
- stop: cancel_command().
- component_status: check is_command_running().
- reached_target event: result callback on the action client.

The component owns its own state. It accesses the shared ROS 2 node
via self.parent.node, which the adapter creates in __init__.
"""

from __future__ import annotations

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
class Ros2Navigation:
    """Canonical RoIS Navigation component backed by Kachaka ROS 2 actions."""

    def __init__(self, config: dict) -> None:
        self._nav_busy = False
        self._nav_target = ""
        self._time_limit = 0
        self._routing_policy = "time"

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
        if self.parent.node.is_command_running():
            return results.status("BUSY")
        return results.status("READY")

    @invoke("execute")
    async def navigate(self, parameters):
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
        locations = self.parent.node.get_locations()
        if locations is None:
            return InvokeResponse(
                return_code=ReturnCode.BAD_PARAMETER, command_id="",
            )
        loc = next(
            (l for l in locations if l["name"] == target or l["id"] == target),
            None,
        )
        if loc is None:
            return InvokeResponse(
                return_code=ReturnCode.BAD_PARAMETER, command_id="",
            )
        accepted = self.parent.node.send_move_to_location(loc["id"])
        if not accepted:
            return InvokeResponse(
                return_code=ReturnCode.ERROR, command_id="",
            )
        self._nav_busy = True
        self._nav_target = target
        return InvokeResponse(
            return_code=ReturnCode.OK, command_id="cmd-nav",
        )

    @invoke("stop")
    async def stop(self, parameters):
        self.parent.node.cancel_command()
        self._nav_busy = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("reached_target")
    async def on_reached(self):
        """Register a result callback on the node."""
        def on_action_result(success: bool) -> None:
            self._nav_busy = False
            target_name = self._nav_target
            self.parent.emit(
                "Navigation",
                "reached_target",
                results.reached_target(
                    target=target_name, is_final_target=True,
                ),
            )
            logger.info(
                "Fired reached_target event (success=%s)", success,
            )

        self.parent.node.set_result_callback(on_action_result)