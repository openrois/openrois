"""PersonDetection component for RealSense cameras (ROS 2).

Publishes the number of detected persons from the ROS 2 perception
pipeline topic /person_detection/count (std_msgs/Int32) as the RoIS
person_detected event.

The component owns its own rclpy Node, created in connect() and torn
down in disconnect(). The node subscribes to the count topic in the
background and emits the event from the ROS callback via the
thread-safe emit() (no-op when nobody is subscribed).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import ReturnCode
from openrois_components_core import component, invoke, query, results, subscribe

logger = logging.getLogger(__name__)


@component("PersonDetection")
class Ros2PersonDetection:
    """Person count from the ROS 2 perception pipeline (RealSense)."""

    def __init__(self, config: dict) -> None:
        self._node_name = config.get("ros2_node_name", "openrois_realsense")
        self._count_topic = config.get(
            "person_count_topic", "/person_detection/count",
        )
        self._node = None
        self._connected = False
        self._running = False
        self._suspended = False

    async def connect(self) -> None:
        """Create the rclpy node and subscribe to the person count topic."""
        import rclpy
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from std_msgs.msg import Int32

        if not rclpy.ok():
            rclpy.init()

        self._node = Node(f"{self._node_name}_person_detection")
        cb_group = ReentrantCallbackGroup()
        # Publisher is RELIABLE/VOLATILE: either reliability works on
        # the subscriber side; BEST_EFFORT avoids head-of-line blocking.
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=5,
        )
        self._node.create_subscription(
            Int32,
            self._count_topic,
            self._on_count,
            sensor_qos,
            callback_group=cb_group,
        )
        self._connected = True
        self._running = True
        logger.info("PersonDetection subscribed to %s", self._count_topic)

    async def disconnect(self) -> None:
        """Tear down the rclpy node."""
        self._connected = False
        if self._node is not None:
            self._node.destroy_node()
            self._node = None

    @property
    def node(self):
        """Expose the rclpy node for WsClient's background spin."""
        return self._node

    def _on_count(self, msg) -> None:
        """Emit person_detected from the ROS count callback."""
        if not self._running or self._suspended:
            return
        timestamp = datetime.now(timezone.utc).isoformat()
        self.parent.emit(  # type: ignore[attr-defined]
            "PersonDetection",
            "person_detected",
            results.person_detected(timestamp=timestamp, number=msg.data),
        )

    @query("component_status")
    async def component_status(self):
        if not self._connected:
            return results.status("ERROR")
        if self._suspended:
            return results.status("READY")
        return results.status("READY")

    @invoke("start")
    async def start(self, parameters):
        self._running = True
        self._suspended = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("stop")
    async def stop(self, parameters):
        self._running = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("suspend")
    async def suspend(self, parameters):
        self._suspended = True
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("resume")
    async def resume(self, parameters):
        self._suspended = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("person_detected")
    async def on_person_detected(self):
        """No-op: events are emitted from the ROS callback.

        The subscribe handler exists so the framework registers the
        subscription in the emitter. The actual event emission happens
        in the ROS callback, so events fire regardless of when the
        operator subscribes.
        """
        pass