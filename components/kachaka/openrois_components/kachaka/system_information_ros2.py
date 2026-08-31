"""SystemInformation component for the Kachaka robot (ROS 2).

Status and location of the Kachaka robot via ROS 2. The component
owns its own rclpy Node, created in connect() and torn down in
disconnect(). No dependency on the adapter for shared state.

robot_position is a poll-on-demand query. Each call reads the cached
pose from the node. The node subscribes to the odometry topic in the
background and caches the latest pose. No extra requests are made
when the app polls.
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, timezone

from openrois_components_core import component, query, results

logger = logging.getLogger(__name__)


@component("SystemInformation")
class Ros2SystemInformation:
    """Status and location of the Kachaka robot via ROS 2."""

    def __init__(self, config: dict) -> None:
        self._engine_id = config.get("engine", {}).get("id", "robot_1")
        self._node_name = config.get("ros2_node_name", "openrois_kachaka")
        self._pose_topic = config.get(
            "robot_pose_topic", "/kachaka/odometry/odometry",
        )
        self._node = None
        self._connected = False
        self._init_time = datetime.now(timezone.utc).isoformat()

    async def connect(self) -> None:
        """Create the rclpy node and subscribe to odometry."""
        import rclpy
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from nav_msgs.msg import Odometry

        if not rclpy.ok():
            rclpy.init()

        self._node = Node(f"{self._node_name}_sysinfo")
        self._lock = threading.Lock()
        self._latest_pose: tuple[float, float, float] | None = None

        cb_group = ReentrantCallbackGroup()
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=5,
        )
        self._node.create_subscription(
            Odometry,
            self._pose_topic,
            self._on_odometry,
            sensor_qos,
            callback_group=cb_group,
        )
        self._connected = True
        logger.info("SystemInformation subscribed to %s", self._pose_topic)

    async def disconnect(self) -> None:
        """Tear down the rclpy node."""
        self._connected = False
        if self._node is not None:
            self._node.destroy_node()
            self._node = None

    def _on_odometry(self, msg) -> None:
        """Cache the latest robot pose from odometry."""
        pos = msg.pose.pose.position
        q = msg.pose.pose.orientation
        yaw = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )
        with self._lock:
            self._latest_pose = (pos.x, pos.y, yaw)

    def _get_pose(self) -> tuple[float, float, float] | None:
        with self._lock:
            return self._latest_pose

    @query("robot_position")
    async def robot_position(self):
        pose = self._get_pose() if self._connected else None
        if pose is None:
            pose = (0.0, 0.0, 0.0)
        timestamp = datetime.now(timezone.utc).isoformat()
        return results.robot_position(
            x=round(pose[0], 4), y=round(pose[1], 4), theta=round(pose[2], 4),
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
        if self._get_pose() is None:
            return results.status("UNINITIALIZED")
        return results.status("READY")