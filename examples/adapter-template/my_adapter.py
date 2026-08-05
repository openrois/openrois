"""Adapter template: starting point for writing your own OpenRoIS adapter.

Copy this file, rename the class, and fill in the # IMPLEMENT YOUR CODE HERE #
blocks with your robot's API calls.

Usage:
    python my_adapter.py --config profile.yaml
"""

from __future__ import annotations

import argparse
import logging

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import ReturnCode
from openrois.sdk import (
    AdapterFramework,
    RobotAdapter,
    component,
    invoke,
    load_config,
    query,
    results,
    subscribe,
)

logger = logging.getLogger(__name__)


class MyAdapter(RobotAdapter):
    """Adapter for your robot.

    Rename this class and fill in the component handlers below.
    Access adapter-level state from component handlers via self.parent
    (e.g., self.parent.nav_client).
    """

    def __init__(self, config: dict) -> None:
        # IMPLEMENT YOUR CODE HERE
        # Initialize your robot's API client (ROS 2 node, HTTP session, etc.).
        # If using ROS 2, create the node here and assign it to self.node
        # so the framework can spin it in a background thread.
        # Example:
        #   import rclpy
        #   rclpy.init()
        #   self.node = rclpy.create_node("openrois_adapter")
        super().__init__(config)

    # ─── SystemInformation (shared read, no bind) ──────────────

    @component("SystemInformation", bind_required=False)
    class SystemInformation:

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

    # ─── Navigation (exclusive, bind required, BUSY) ───────────

    @component("Navigation", bind_required=True)
    class Navigation:

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
            # IMPLEMENT YOUR CODE HERE
            # Return "BUSY" if navigating, "READY" if idle.
            return results.status("READY")

        @invoke("EXECUTE")
        async def navigate(self, parameters):
            # IMPLEMENT YOUR CODE HERE
            # parameters[0].value is the target WayPoint name.
            # Call your robot's navigation API.
            # Return InvokeResponse with a command_id.
            raise NotImplementedError

        @invoke("STOP")
        async def stop(self, parameters):
            # IMPLEMENT YOUR CODE HERE
            # Cancel the current navigation.
            raise NotImplementedError

        @subscribe("reached_target")
        async def on_reached(self):
            # Called once when an operator subscribes.
            # Do setup here if needed (e.g., start monitoring).
            # Use self.parent.emit("reached_target", results.reached_target(...))
            # to push events when navigation completes.
            pass

    # ─── ObjectDetection (shared read, no bind) ───────────────

    @component("ObjectDetection", bind_required=False)
    class ObjectDetection:

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
            # Use self.parent.emit("object_detected", results.detection(...))
            # to push events when new detections arrive.
            pass

    # ─── ObjectManipulation (exclusive, bind required, BUSY) ──

    @component("ObjectManipulation", bind_required=True)
    class ObjectManipulation:

        @query("component_status")
        async def status(self):
            # IMPLEMENT YOUR CODE HERE
            # Return "BUSY" if the arm is moving, "READY" if idle.
            return results.status("READY")

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

        @invoke("EXECUTE")
        async def execute(self, parameters):
            # IMPLEMENT YOUR CODE HERE
            # parameters[0].value is the command: "grasp" or "place".
            # For grasp: parameters[1].value is the object_id.
            # For place: parameters[1].value is object_id,
            #            parameters[2].value is plane_id,
            #            parameters[3].value is x, parameters[4].value is y.
            raise NotImplementedError

        @invoke("STOP")
        async def stop(self, parameters):
            # IMPLEMENT YOUR CODE HERE
            # Cancel the current arm motion.
            raise NotImplementedError

        @subscribe("manipulation_complete")
        async def on_complete(self):
            # Called once when an operator subscribes.
            # Use self.parent.emit("manipulation_complete",
            #     results.manipulation_complete(success=True))
            # to push events when manipulation finishes.
            pass


def main() -> None:
    """Entry point: load config, create adapter, run framework."""
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="OpenRoIS adapter")
    parser.add_argument(
        "--config",
        default="profile.yaml",
        help="Path to the profile YAML file (default: profile.yaml)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    adapter = MyAdapter(config)
    framework = AdapterFramework(adapter, config)
    framework.run()


if __name__ == "__main__":
    main()