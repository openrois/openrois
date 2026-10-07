"""Navigation for the Kachaka, over ROS 2.

``start`` drives to the first of ``target_positions``, a location of the Kachaka named by
its name or its id, with the ``ExecKachakaCommand`` action, and runs until the action
ends. ``stop`` cancels the goal. The locations come from the latched location list topic.

The component owns its rclpy node, created in ``connect()``. The engine's WebSocket
client spins it, as ``_node``, in a background thread, so the ROS 2 callbacks only hand
their results to the event loop with ``call_soon_threadsafe``, and every decision about a
goal is taken on the event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from typing import Any

from openrois.components.core import CommandFailed, Component, component, invoke, subscribe
from openrois.interfaces.components import NAVIGATION_PROFILE
from openrois.interfaces.service import CompletedStatus

logger = logging.getLogger(__name__)


@component(NAVIGATION_PROFILE)
class Ros2Navigation(Component):
    """Navigation backed by the Kachaka ROS 2 interfaces.

    Args:
        node_name: The name of the rclpy node, which gets a ``_nav`` suffix.
        locations_topic: The latched topic that lists the locations.
        command_action: The action that runs Kachaka commands.
        goal_timeout: Seconds to wait for the Kachaka to accept or refuse a goal.
    """

    def __init__(
        self,
        *,
        node_name: str = "openrois_kachaka",
        locations_topic: str = "/kachaka/layout/locations/list",
        command_action: str = "/kachaka/kachaka_command/execute",
        goal_timeout: float = 10.0,
    ) -> None:
        self._node_name = node_name
        self._locations_topic = locations_topic
        self._command_action = command_action
        self._goal_timeout = goal_timeout
        self._node: Any = None
        self._action_client: Any = None
        self._lock = threading.Lock()
        # The locations by name and by id, from the latest message of the topic.
        self._locations: dict[str, str] = {}
        # The accepted goal of the running drive. Only the event loop reads and writes it.
        self._goal_handle: Any = None

    async def connect(self) -> None:
        import rclpy
        from kachaka_interfaces.action import ExecKachakaCommand
        from kachaka_interfaces.msg import LocationList
        from rclpy.action import ActionClient
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

        if not rclpy.ok():
            rclpy.init()
        node = Node(f"{self._node_name}_nav")
        try:
            callbacks = ReentrantCallbackGroup()
            latched = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                depth=1,
            )
            node.create_subscription(
                LocationList, self._locations_topic, self._on_locations, latched,
                callback_group=callbacks,
            )
            self._action_client = ActionClient(
                node, ExecKachakaCommand, self._command_action, callback_group=callbacks
            )
        except Exception:
            # A node that is half set up is not spun.
            node.destroy_node()
            raise
        self._node = node
        logger.info(
            "Navigation listens on %s and sends goals to %s",
            self._locations_topic,
            self._command_action,
        )

    async def disconnect(self) -> None:
        if self._node is None:
            return
        # The node leaves the executor that spins it before it is destroyed, and the
        # action client goes with the node rather than on its own, which the spinning
        # thread might still be polling.
        executor = getattr(self._node, "executor", None)
        if executor is not None:
            executor.remove_node(self._node)
        self._action_client = None
        self._node.destroy_node()
        self._node = None

    @invoke("start")
    async def start(self) -> None:
        from kachaka_interfaces.action import ExecKachakaCommand
        from kachaka_interfaces.msg import KachakaCommand

        targets = self.parameters.get("target_positions", [])
        if not targets:
            raise CommandFailed(CompletedStatus.ERROR, "target_positions is empty")
        target = targets[0]
        with self._lock:
            location_id = self._locations.get(target)
        if location_id is None:
            raise CommandFailed(CompletedStatus.ERROR, f"The Kachaka knows no location {target!r}")
        if not self._action_client.server_is_ready():
            raise CommandFailed(CompletedStatus.ERROR, "The Kachaka command action is not ready")

        goal = ExecKachakaCommand.Goal()
        goal.kachaka_command.command_type = KachakaCommand.MOVE_TO_LOCATION_COMMAND
        goal.kachaka_command.move_to_location_command_target_location_id = location_id
        loop = asyncio.get_running_loop()
        answered: asyncio.Future[Any] = loop.create_future()
        logger.info("Driving to %s", target)
        self._action_client.send_goal_async(goal).add_done_callback(
            lambda sent: loop.call_soon_threadsafe(_settle, answered, _accepted(sent))
        )
        goal_handle = await self._wait_for_answer(answered)
        if goal_handle is None:
            raise CommandFailed(CompletedStatus.ERROR, "The Kachaka refused the goal")

        ended: asyncio.Future[bool] = loop.create_future()
        self._goal_handle = goal_handle
        goal_handle.get_result_async().add_done_callback(
            lambda finished: loop.call_soon_threadsafe(_settle, ended, _succeeded(finished))
        )
        try:
            success = await ended
        except asyncio.CancelledError:
            # A stop cancelled the goal already. When the engine shuts down, nothing
            # else halts the robot.
            await self._cancel(self._goal_handle)
            raise
        finally:
            if self._goal_handle is goal_handle:
                self._goal_handle = None
        if not success:
            raise CommandFailed(CompletedStatus.ERROR, f"The drive to {target} failed")
        self.emit("reached_target", target=target, is_final_target=True)

    @invoke("stop")
    async def stop(self) -> None:
        await self._cancel(self._goal_handle)

    @subscribe("reached_target")
    async def reached_target(self) -> None:
        pass  # start emits the event when the drive ends.

    async def _wait_for_answer(self, answered: asyncio.Future[Any]) -> Any:
        """The accepted goal handle, or None when the Kachaka refused the goal.

        A start cancelled while it waits, by a stop or a new start, still waits for the
        answer and cancels the goal, so the goal is cancelled before the start ends and
        before a new start sends its own goal.
        """
        try:
            async with asyncio.timeout(self._goal_timeout):
                return await asyncio.shield(answered)
        except TimeoutError:
            answered.add_done_callback(_cancel_late_goal)
            raise CommandFailed(
                CompletedStatus.ERROR, "The Kachaka did not answer the goal in time"
            ) from None
        except asyncio.CancelledError:
            # The goal is cancelled as soon as the answer comes, even when this start
            # is cancelled again while it waits for the answer.
            answered.add_done_callback(_cancel_late_goal)
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(self._goal_timeout):
                    await asyncio.shield(answered)
            raise

    async def _cancel(self, goal_handle: Any) -> None:
        """Cancel a goal and wait, within the goal timeout, until the Kachaka confirms.

        Waiting keeps the node alive until the request has gone out, also when the
        engine shuts down right after.
        """
        if goal_handle is None or self._goal_handle is not goal_handle:
            return
        self._goal_handle = None
        loop = asyncio.get_running_loop()
        confirmed: asyncio.Future[None] = loop.create_future()
        goal_handle.cancel_goal_async().add_done_callback(
            lambda _: loop.call_soon_threadsafe(_settle, confirmed, None)
        )
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(self._goal_timeout):
                await asyncio.shield(confirmed)

    def _on_locations(self, message: Any) -> None:
        """Keep the latest locations. Runs on the thread that spins the node."""
        locations: dict[str, str] = {}
        for location in message.locations:
            locations[location.id] = location.id
            locations[location.name] = location.id
        with self._lock:
            self._locations = locations
        logger.info("Received %d locations", len(message.locations))


def _accepted(sent: Any) -> Any:
    """The goal handle of an accepted goal, or None. Runs on the thread of the node."""
    try:
        goal_handle = sent.result()
    except Exception:
        logger.exception("The goal request failed")
        return None
    return goal_handle if goal_handle is not None and goal_handle.accepted else None


def _succeeded(finished: Any) -> bool:
    """Whether an action ended with success. Runs on the thread of the node."""
    try:
        response = finished.result()
    except Exception:
        logger.exception("The goal result could not be read")
        return False
    # The response of an action carries the action's result in ``result``.
    result = getattr(response, "result", response)
    return bool(getattr(result, "success", False))


def _settle[T](future: asyncio.Future[T], value: T) -> None:
    """Resolve a future the event loop waits on, unless it was cancelled meanwhile."""
    if not future.done():
        future.set_result(value)


def _cancel_late_goal(answered: asyncio.Future[Any]) -> None:
    """Cancel a goal the Kachaka accepted after its start stopped waiting for it."""
    if answered.cancelled():
        return
    goal_handle = answered.result()
    if goal_handle is not None:
        goal_handle.cancel_goal_async()
