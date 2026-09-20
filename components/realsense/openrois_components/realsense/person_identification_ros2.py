"""PersonIdentification component for RealSense cameras (ROS 2).

Publishes the tracking ID of each detected person from the ROS 2
perception pipeline topic /person_tracks (vision_msgs/Detection3DArray)
as the RoIS person_identified event.

Identifier semantics (important):
The IDs are ByteTrack session-scoped tracking IDs. They are reset when
the perception pipeline restarts and may switch under occlusion or
person crossing. They are NOT persistent personal identities. Service
applications must not treat them as stable across sessions.

The component owns its own rclpy Node, created in connect() and torn
down in disconnect(). The node subscribes to the tracks topic in the
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


@component("PersonIdentification")
class Ros2PersonIdentification:
    """Per-person tracking IDs from the ROS 2 perception pipeline (RealSense)."""

    def __init__(self, config: dict) -> None:
        self._node_name = config.get("ros2_node_name", "openrois_realsense")
        self._tracks_topic = config.get("person_tracks_topic", "/person_tracks")
        self._node = None
        self._connected = False
        self._running = False
        self._suspended = False

    async def connect(self) -> None:
        """Create the rclpy node and subscribe to the person tracks topic."""
        import rclpy
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from vision_msgs.msg import Detection3DArray

        if not rclpy.ok():
            rclpy.init()

        self._node = Node(f"{self._node_name}_person_identification")
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
        self._connected = True
        self._running = True
        logger.info("PersonIdentification subscribed to %s", self._tracks_topic)

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

    def _on_tracks(self, msg) -> None:
        """Emit person_identified from the ROS tracks callback."""
        if not self._running or self._suspended:
            return

        identifiers: list[dict[str, object]] = []
        for det in msg.detections:
            identifiers.append({"id": det.id, "name": ""})

        timestamp = datetime.now(timezone.utc).isoformat()
        self.parent.emit(  # type: ignore[attr-defined]
            "PersonIdentification",
            "person_identified",
            results.person_identified(timestamp=timestamp, identifiers=identifiers),
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

    @subscribe("person_identified")
    async def on_person_identified(self):
        """No-op: events are emitted from the ROS callback.

        The subscribe handler exists so the framework registers the
        subscription in the emitter. The actual event emission happens
        in the ROS callback, so events fire regardless of when the
        operator subscribes.
        """
        pass