"""SystemInformation for the Kachaka, over ROS 2.

``robot_position`` answers with the latest pose of the odometry topic, which the node
receives in the background. The component owns its rclpy node, created in
``connect()``, and the engine's WebSocket client spins it as ``_node``.
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import UTC, datetime
from typing import Any

from openrois.components.core import Component, component, query
from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components import SYSTEM_INFORMATION_PROFILE

logger = logging.getLogger(__name__)


@component(SYSTEM_INFORMATION_PROFILE)
class Ros2SystemInformation(Component):
    """SystemInformation backed by the Kachaka ROS 2 interfaces.

    Args:
        node_name: The name of the rclpy node, which gets a ``_sysinfo`` suffix.
        pose_topic: The odometry topic of the Kachaka.
    """

    def __init__(
        self,
        *,
        node_name: str = "openrois_kachaka",
        pose_topic: str = "/kachaka/odometry/odometry",
    ) -> None:
        self._node_name = node_name
        self._pose_topic = pose_topic
        self._node: Any = None
        self._lock = threading.Lock()
        self._pose: tuple[float, float, float, datetime] | None = None
        self._started = datetime.now(UTC)

    async def connect(self) -> None:
        import rclpy
        from nav_msgs.msg import Odometry
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

        if not rclpy.ok():
            rclpy.init()
        node = Node(f"{self._node_name}_sysinfo")
        try:
            sensor = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
                depth=5,
            )
            node.create_subscription(
                Odometry, self._pose_topic, self._on_odometry, sensor,
                callback_group=ReentrantCallbackGroup(),
            )
        except Exception:
            # A node that is half set up is not spun.
            node.destroy_node()
            raise
        self._node = node
        self._started = datetime.now(UTC)
        logger.info("SystemInformation listens on %s", self._pose_topic)

    async def disconnect(self) -> None:
        if self._node is None:
            return
        # The node leaves the executor that spins it before it is destroyed.
        executor = getattr(self._node, "executor", None)
        if executor is not None:
            executor.remove_node(self._node)
        self._node.destroy_node()
        self._node = None

    @query("robot_position")
    async def robot_position(self) -> dict[str, object]:
        """The latest pose of the Kachaka, ``x,y,theta`` in meters and radians.

        Raises:
            RuntimeError: No odometry message arrived yet, so the query answers ERROR.
        """
        with self._lock:
            pose = self._pose
        if pose is None:
            raise RuntimeError(f"No odometry on {self._pose_topic} yet")
        x, y, theta, measured = pose
        return {
            "position_data": [f"{x:.4f},{y:.4f},{theta:.4f}"],
            "robot_ref": [self.ref.split("/", 1)[0]],
            "timestamp": measured,
        }

    @query("engine_status")
    async def engine_status(self) -> dict[str, object]:
        """READY since the component connected.

        A component that could not connect answers no query, so READY is all it reports.
        """
        return {"operable_time": self._started, "status": ComponentStatus.READY}

    def _on_odometry(self, message: Any) -> None:
        """Keep the latest pose. Runs on the thread that spins the node."""
        position = message.pose.pose.position
        q = message.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        with self._lock:
            self._pose = (position.x, position.y, yaw, datetime.now(UTC))
