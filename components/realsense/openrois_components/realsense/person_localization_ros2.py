"""PersonLocalization component for RealSense cameras (ROS 2).

Publishes the 3D position of each detected person from the ROS 2
perception pipeline topic /person_tracks (vision_msgs/Detection3DArray)
as the RoIS person_localized event.

Coordinate frame handling (plan B, agreed with the ROS 2 side):
The source frame is camera_color_optical_frame (+x right, +y down,
+z forward). The RoIS contract expects the robot body frame
(REP-103: +x forward, +y left, +z up). This component applies the
static transform from /tf_static (published by the camera driver)
to convert positions into the target frame (default: camera_link)
before emitting.

The component owns its own rclpy Node, created in connect() and torn
down in disconnect(). The node subscribes to the tracks topic and to
/tf_static in the background and emits the event from the ROS callback
via the thread-safe emit() (no-op when nobody is subscribed).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import ReturnCode
from openrois_components_core import component, invoke, query, results, subscribe

logger = logging.getLogger(__name__)


@component("PersonLocalization")
class Ros2PersonLocalization:
    """Per-person 3D positions from the ROS 2 perception pipeline (RealSense)."""

    def __init__(self, config: dict) -> None:
        self._node_name = config.get("ros2_node_name", "openrois_realsense")
        self._tracks_topic = config.get("person_tracks_topic", "/person_tracks")
        self._source_frame = config.get(
            "person_tracks_frame", "camera_color_optical_frame",
        )
        self._target_frame = config.get("person_position_frame", "camera_link")
        self._node = None
        self._connected = False
        self._running = False
        self._suspended = False
        self._tf_buffer = None
        self._tf_listener = None

    async def connect(self) -> None:
        """Create the rclpy node, subscribe to tracks and /tf_static."""
        import rclpy
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from tf2_ros import Buffer, TransformListener
        from vision_msgs.msg import Detection3DArray

        if not rclpy.ok():
            rclpy.init()

        self._node = Node(f"{self._node_name}_person_localization")
        cb_group = ReentrantCallbackGroup()
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=5,
        )
        self._node.create_subscription(
            Detection3DArray,
            self._tracks_topic,
            self._on_tracks,
            sensor_qos,
            callback_group=cb_group,
        )

        # TF: static transforms are latched with TRANSIENT_LOCAL.
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self._node)

        self._connected = True
        self._running = True
        logger.info(
            "PersonLocalization subscribed to %s (frame %s -> %s)",
            self._tracks_topic, self._source_frame, self._target_frame,
        )

    async def disconnect(self) -> None:
        """Tear down the rclpy node."""
        self._connected = False
        if self._node is not None:
            self._node.destroy_node()
            self._node = None
        self._tf_buffer = None
        self._tf_listener = None

    @property
    def node(self):
        """Expose the rclpy node for WsClient's background spin."""
        return self._node

    def _transform_to_target(self, x: float, y: float, z: float) -> tuple[float, float, float] | None:
        """Transform a point from the source frame to the target frame.

        Returns None when the transform is not (yet) available; the
        caller skips the detection in that case.
        """
        if self._source_frame == self._target_frame:
            return (x, y, z)
        try:
            from geometry_msgs.msg import PointStamped
            point = PointStamped()
            point.header.frame_id = self._source_frame
            point.point.x = x
            point.point.y = y
            point.point.z = z
            transformed = self._tf_buffer.transform(
                point, self._target_frame, timeout=None,
            )
            return (
                transformed.point.x,
                transformed.point.y,
                transformed.point.z,
            )
        except Exception as exc:
            logger.debug("TF transform unavailable: %s", exc)
            return None

    def _on_tracks(self, msg) -> None:
        """Emit person_localized from the ROS tracks callback."""
        if not self._running or self._suspended:
            return

        positions: list[dict[str, object]] = []
        for det in msg.detections:
            pos = det.bbox.center.position
            transformed = self._transform_to_target(pos.x, pos.y, pos.z)
            if transformed is None:
                continue
            positions.append({
                "id": det.id,
                "x": round(transformed[0], 4),
                "y": round(transformed[1], 4),
                "z": round(transformed[2], 4),
            })

        timestamp = datetime.now(timezone.utc).isoformat()
        self.parent.emit(  # type: ignore[attr-defined]
            "PersonLocalization",
            "person_localized",
            results.person_localized(timestamp=timestamp, positions=positions),
        )

    @query("component_status")
    async def component_status(self):
        if not self._connected:
            return results.status("ERROR")
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

    @subscribe("person_localized")
    async def on_person_localized(self):
        """No-op: events are emitted from the ROS callback.

        The subscribe handler exists so the framework registers the
        subscription in the emitter. The actual event emission happens
        in the ROS callback, so events fire regardless of when the
        operator subscribes.
        """
        pass