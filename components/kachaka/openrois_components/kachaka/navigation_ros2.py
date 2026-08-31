"""Navigation component for the Kachaka robot (ROS 2).

Translates RoIS Navigation commands to Kachaka ROS 2 action calls:
- set_parameter: set target_positions, time_limit, routing_policy.
- start: begin navigating to the set target (send_move_to_location).
- stop: cancel the current navigation command.
- component_status: check is_command_running().
- reached_target event: result callback on the action client.

The component owns its own rclpy Node, created in connect() and torn
down in disconnect(). No dependency on the adapter for shared state.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Callable

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import ReturnCode, Result
from openrois_components_core import component, invoke, query, results, subscribe

logger = logging.getLogger(__name__)


@component(
    "Navigation",
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
        self._node_name = config.get("ros2_node_name", "openrois_kachaka")
        self._locations_topic = config.get(
            "locations_topic", "/kachaka/layout/locations/list",
        )
        self._command_action = config.get(
            "command_action", "/kachaka/kachaka_command/execute",
        )
        self._nav_busy = False
        self._nav_target = ""
        self._time_limit = 0
        self._routing_policy = "time"
        self._node = None
        self._connected = False

        # Set up the action result callback at init time so it always
        # fires when navigation completes, regardless of whether the
        # operator has subscribed to reached_target yet. The emit()
        # call is a no-op if there are no subscribers.
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

        self._on_action_result = on_action_result

    async def connect(self) -> None:
        """Create the rclpy node, subscribe to locations, create action client."""
        import rclpy
        from rclpy.action import ActionClient
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from kachaka_interfaces.msg import LocationList
        from kachaka_interfaces.action import ExecKachakaCommand

        if not rclpy.ok():
            rclpy.init()

        self._node = Node(f"{self._node_name}_nav")
        self._lock = threading.Lock()
        self._latest_locations: list[dict] | None = None
        self._command_running = False
        self._goal_handle = None

        cb_group = ReentrantCallbackGroup()

        latched_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            depth=1,
        )
        self._node.create_subscription(
            LocationList,
            self._locations_topic,
            self._on_locations,
            latched_qos,
            callback_group=cb_group,
        )

        self._action_client = ActionClient(
            self._node,
            ExecKachakaCommand,
            self._command_action,
            callback_group=cb_group,
        )
        self._connected = True
        logger.info(
            "Navigation subscribed to %s, action client for %s",
            self._locations_topic, self._command_action,
        )

    async def disconnect(self) -> None:
        """Tear down the rclpy node."""
        self._connected = False
        if self._node is not None:
            self._node.destroy_node()
            self._node = None

    def _on_locations(self, msg) -> None:
        """Cache the latest location list."""
        locations = []
        for loc in msg.locations:
            locations.append({
                "id": loc.id,
                "name": loc.name,
                "x": loc.pose.x,
                "y": loc.pose.y,
                "theta": loc.pose.theta,
            })
        with self._lock:
            self._latest_locations = locations
        logger.info("Received %d locations", len(locations))

    def _get_locations(self) -> list[dict] | None:
        with self._lock:
            return self._latest_locations

    def _is_command_running(self) -> bool:
        with self._lock:
            return self._command_running

    def _set_result_callback(self, callback: Callable[[bool], None]) -> None:
        with self._lock:
            self._on_result = callback

    def _send_move_to_location(self, location_id: str) -> bool:
        """Send a move_to_location command via the action client."""
        from kachaka_interfaces.action import ExecKachakaCommand
        from kachaka_interfaces.msg import KachakaCommand

        if not self._action_client.server_is_ready():
            logger.error("Action server not available")
            return False

        goal_msg = ExecKachakaCommand.Goal()
        goal_msg.kachaka_command.command_type = (
            KachakaCommand.MOVE_TO_LOCATION_COMMAND
        )
        goal_msg.kachaka_command.move_to_location_command_target_location_id = (
            location_id
        )

        with self._lock:
            self._command_running = True

        self._action_client.send_goal_async(
            goal_msg,
            feedback_callback=lambda _: None,
        ).add_done_callback(self._on_goal_response)
        return True

    def _on_goal_response(self, future) -> None:
        """Handle goal acceptance/rejection."""
        goal_handle = future.result()
        if not goal_handle.accepted:
            logger.warning("Action goal rejected")
            with self._lock:
                self._command_running = False
            return
        logger.info("Action goal accepted")
        with self._lock:
            self._goal_handle = goal_handle
        goal_handle.get_result_async().add_done_callback(self._on_result_callback)

    def _on_result_callback(self, future) -> None:
        """Handle action completion. Emit reached_target event."""
        result = future.result()
        success = result.success if result is not None else False
        logger.info("Action completed (success=%s)", success)

        with self._lock:
            self._command_running = False
            self._goal_handle = None
            callback = self._on_result
            self._on_result = None

        if callback is not None:
            callback(success)

    def _cancel_command(self) -> None:
        """Cancel the current command via the action goal handle."""
        with self._lock:
            self._command_running = False
            goal_handle = self._goal_handle
            self._goal_handle = None

        if goal_handle is not None:
            goal_handle.cancel_goal_async()
            logger.info("Cancel sent to action server")
        else:
            logger.info("Cancel requested but no active goal")

    @query("get_parameter")
    async def get_parameter(self):
        """Return current parameter values: target_positions, time_limit, routing_policy."""
        target_positions = [self._nav_target] if self._nav_target else []
        return [
            Result(
                name="target_positions",
                data_type_ref="string[]",
                value=json.dumps(target_positions, ensure_ascii=False),
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
        if not self._connected:
            return results.status("ERROR")
        if self._is_command_running():
            return results.status("BUSY")
        return results.status("READY")

    @invoke("start")
    async def start(self, parameters):
        """Begin navigating to the target set via set_parameter.

        If target_positions are passed directly in parameters, parse
        them by name. Otherwise use the target stored by set_parameter.
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
        locations = self._get_locations()
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
        accepted = self._send_move_to_location(loc["id"])
        if not accepted:
            return InvokeResponse(
                return_code=ReturnCode.ERROR, command_id="",
            )
        self._nav_busy = True
        self._nav_target = target
        # Ensure the result callback is set before the action starts.
        self._set_result_callback(self._on_action_result)
        return InvokeResponse(
            return_code=ReturnCode.OK, command_id="cmd-nav",
        )

    @invoke("stop")
    async def stop(self, parameters):
        """Cancel the current navigation command."""
        self._cancel_command()
        self._nav_busy = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("reached_target")
    async def on_reached(self):
        """No-op: the result callback is set in navigate() at init time.

        The subscribe handler exists so the framework registers the
        subscription in the emitter. The actual event emission happens
        in the action result callback set up in __init__ and attached
        in navigate(). This ensures the event fires even if the operator
        subscribes after execute completes.
        """
        pass