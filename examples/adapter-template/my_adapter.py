"""Adapter template: starting point for writing your own OpenRoIS adapter.

Copy this file, rename the class, and fill in the # IMPLEMENT YOUR CODE HERE #
blocks with your robot's API calls.

Usage:
    python my_adapter.py --config openrois-profile.yaml
"""

from __future__ import annotations

import argparse
import logging

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import ReturnCode
from openrois_core import Engine, WsClient, component_config, read_profile
from openrois_components_core import (
    component,
    invoke,
    meta_from_decorators,
    query,
    results,
    subscribe,
)

logger = logging.getLogger(__name__)


# ─── SystemInformation (shared read, no bind) ────────────────

@component("SystemInformation")
class SystemInformation:

    def __init__(self, config: dict) -> None:
        # IMPLEMENT YOUR CODE HERE
        # Read per-component config from the config dict.
        # Example: self._grpc_server = config.get("grpc_server", "...")
        pass

    async def connect(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        # Create your robot's API client (gRPC, ROS 2 node, etc.).
        pass

    async def disconnect(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        # Tear down the API client.
        pass

    @query("robot_position")
    async def robot_position(self):
        # IMPLEMENT YOUR CODE HERE
        # Call your robot's API to get the position.
        # Example: return results.position(x=3.2, y=1.8, theta=0.5)
        raise NotImplementedError

    @query("battery_level")
    async def battery_level(self):
        # IMPLEMENT YOUR CODE HERE
        # Example: return results.battery_level(percentage=85.5)
        raise NotImplementedError

    @query("component_status")
    async def status(self):
        return results.status("READY")


# ─── Navigation (exclusive, bind required, BUSY) ─────────────

@component("Navigation", function="actuation")
class Navigation:

    def __init__(self, config: dict) -> None:
        # IMPLEMENT YOUR CODE HERE
        self._busy = False

    async def connect(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        pass

    async def disconnect(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        pass

    @query("waypoints")
    async def get_waypoints(self):
        # IMPLEMENT YOUR CODE HERE
        # Example:
        #   return results.waypoints([
        #       {"id": "desk", "name": "desk", "x": 2.0, "y": 1.5},
        #   ])
        raise NotImplementedError

    @query("component_status")
    async def status(self):
        # Return "BUSY" if navigating, "READY" if idle.
        return results.status("BUSY" if self._busy else "READY")

    @invoke("execute")
    async def navigate(self, parameters):
        # IMPLEMENT YOUR CODE HERE
        # parameters[0].value is the target WayPoint name.
        # Call your robot's navigation API.
        # Return InvokeResponse with a command_id.
        raise NotImplementedError

    @invoke("stop")
    async def stop(self, parameters):
        # IMPLEMENT YOUR CODE HERE
        # Cancel the current navigation.
        self._busy = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("reached_target")
    async def on_reached(self):
        # Called once when an operator subscribes.
        # Do setup here if needed (e.g., start monitoring).
        # Use self.parent.emit_async("Navigation", "reached_target",
        #     results.reached_target(...))
        # to push events when navigation completes.
        pass


# ─── ObjectDetection (shared read, no bind) ──────────────────

@component("ObjectDetection", function="sensing")
class ObjectDetection:

    def __init__(self, config: dict) -> None:
        # IMPLEMENT YOUR CODE HERE
        pass

    async def connect(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        pass

    async def disconnect(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        pass

    @query("list_objects")
    async def list_objects(self):
        # IMPLEMENT YOUR CODE HERE
        # Return the latest detections as Result lists.
        # Example:
        #   return [
        #       *results.detection(
        #           object_id="0",
        #           object_class="person",
        #           bounding_box=[[0.1, 0.2], [0.3, 0.2], [0.3, 0.4], [0.1, 0.4]],
        #       )
        #   ]
        raise NotImplementedError

    @query("component_status")
    async def status(self):
        return results.status("READY")

    @subscribe("object_detected")
    async def on_object_detected(self):
        # Called once when an operator subscribes.
        # Use self.parent.emit_async("ObjectDetection", "object_detected",
        #     results.detection(...))
        # to push events when new detections arrive.
        pass


# ─── ObjectManipulation (exclusive, bind required, BUSY) ────

@component("ObjectManipulation", function="actuation")
class ObjectManipulation:

    def __init__(self, config: dict) -> None:
        # IMPLEMENT YOUR CODE HERE
        self._busy = False

    async def connect(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        pass

    async def disconnect(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        pass

    @query("component_status")
    async def status(self):
        # Return "BUSY" if the arm is moving, "READY" if idle.
        return results.status("BUSY" if self._busy else "READY")

    @query("gripper_state")
    async def gripper_state(self):
        # IMPLEMENT YOUR CODE HERE
        # Example: return results.gripper_state("open")
        raise NotImplementedError

    @query("current_grasped_object")
    async def current_grasped_object(self):
        # IMPLEMENT YOUR CODE HERE
        # Example: return results.current_grasped_object("obj_42")
        raise NotImplementedError

    @invoke("execute")
    async def execute(self, parameters):
        # IMPLEMENT YOUR CODE HERE
        # parameters[0].value is the command: "grasp" or "place".
        # For grasp: parameters[1].value is the object_id.
        # For place: parameters[1].value is object_id,
        #            parameters[2].value is plane_id,
        #            parameters[3].value is x, parameters[4].value is y.
        raise NotImplementedError

    @invoke("stop")
    async def stop(self, parameters):
        # IMPLEMENT YOUR CODE HERE
        # Cancel the current arm motion.
        self._busy = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("manipulation_complete")
    async def on_complete(self):
        # Called once when an operator subscribes.
        # Use self.parent.emit_async("ObjectManipulation",
        #     "manipulation_complete",
        #     results.manipulation_complete(success=True))
        # to push events when manipulation finishes.
        pass


# ─── Component classes to register ───────────────────────────

COMPONENT_CLASSES = [
    SystemInformation,
    Navigation,
    ObjectDetection,
    ObjectManipulation,
]


def main() -> None:
    """Entry point: load profile, create engine, register components, run."""
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="OpenRoIS adapter")
    parser.add_argument(
        "--config",
        default="openrois-profile.yaml",
        help="Path to the profile YAML file (default: openrois-profile.yaml)",
    )
    args = parser.parse_args()

    profile = read_profile(args.config)

    engine = Engine(
        engine_id=profile["engine"]["id"],
        platform=profile["engine"].get("platform", ""),
    )

    for cls in COMPONENT_CLASSES:
        meta = meta_from_decorators(cls)
        engine.register_component(
            meta.ref,
            cls(component_config(profile, meta.ref)),
            meta,
        )

    ws_client = WsClient(engine, profile["engine"]["gateway_url"])
    ws_client.run()


if __name__ == "__main__":
    main()
