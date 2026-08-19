"""Mock adapter for testing the OpenRoIS adapter SDK without a real robot.

Connects to the avatar, registers 4 components, and responds with
hardcoded data. Fires events on a timer to simulate robot activity.

Usage:
    python mock_adapter.py --config openrois-profile.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from openrois.sdk import (
    AdapterFramework,
    InvokeResponse,
    ReturnCode,
    RobotAdapter,
    component,
    invoke,
    load_config,
    query,
    results,
    subscribe,
)

logger = logging.getLogger(__name__)


class MockAdapter(RobotAdapter):
    """Mock adapter with hardcoded responses for all 4 components."""

    def __init__(self, config: dict) -> None:
        self._nav_busy = False
        self._arm_busy = False
        super().__init__(config)

    # ─── SystemInformation ─────────────────────────────────────

    @component("SystemInformation", bind_required=False)
    class SystemInformation:

        @query("robot_position")
        async def robot_position(self):
            return results.position(x=3.2, y=1.8, theta=0.5)

        @query("battery_level")
        async def battery_level(self):
            return results.battery_level(percentage=85.5)

        @query("component_status")
        async def status(self):
            return results.status("READY")

    # ─── Navigation ─────────────────────────────────────────────

    @component("Navigation", bind_required=True)
    class Navigation:

        @query("waypoints")
        async def get_waypoints(self):
            return results.waypoints([
                {"id": "desk", "name": "desk", "x": 2.0, "y": 1.5, "theta": 0.0},
                {"id": "kitchen", "name": "kitchen", "x": 5.0, "y": 3.0, "theta": 1.57},
            ])

        @query("component_status")
        async def status(self):
            return results.status("BUSY" if self.parent._nav_busy else "READY")

        @invoke("execute")
        async def navigate(self, parameters):
            if self.parent._nav_busy:
                return InvokeResponse(return_code=ReturnCode.ERROR, command_id="")
            target = parameters[0].value if parameters else "unknown"
            logger.info("Navigate to: %s", target)
            self.parent._nav_busy = True
            self.parent._nav_target = target
            return InvokeResponse(return_code=ReturnCode.OK, command_id="cmd-nav")

        @invoke("stop")
        async def stop(self, parameters):
            self.parent._nav_busy = False
            return InvokeResponse(return_code=ReturnCode.OK, command_id="")

        @subscribe("reached_target")
        async def on_reached(self):
            # Fire a reached_target event after 5 seconds.
            loop = asyncio.get_event_loop()
            loop.create_task(self._fire_reached())

        async def _fire_reached(self):
            await asyncio.sleep(5.0)
            self.parent._nav_busy = False
            target_name = getattr(self.parent, "_nav_target", "unknown")
            self.parent.emit(  # type: ignore[attr-defined]
                "Navigation",
                "reached_target",
                results.reached_target(
                    target=target_name, is_final_target=True,
                ),
            )
            logger.info("Fired reached_target event")

    # ─── ObjectDetection ───────────────────────────────────────

    @component("ObjectDetection", bind_required=False)
    class ObjectDetection:

        @query("list_objects")
        async def list_objects(self):
            return [
                *results.detection(
                    object_id="0",
                    object_class="person",
                    bounding_box=[[0.1, 0.2], [0.3, 0.2], [0.3, 0.4], [0.1, 0.4]],
                ),
                *results.detection(
                    object_id="1",
                    object_class="cup",
                    bounding_box=[[0.5, 0.5], [0.6, 0.5], [0.6, 0.6], [0.5, 0.6]],
                ),
            ]

        @query("component_status")
        async def status(self):
            return results.status("READY")

        @subscribe("object_detected")
        async def on_object_detected(self):
            # Fire an object_detected event after 3 seconds.
            loop = asyncio.get_event_loop()
            loop.create_task(self._fire_detected())

        async def _fire_detected(self):
            await asyncio.sleep(3.0)
            self.parent.emit(  # type: ignore[attr-defined]
                "ObjectDetection",
                "object_detected",
                results.detection(
                    object_id="2",
                    object_class="bottle",
                    bounding_box=[[0.2, 0.3], [0.4, 0.3], [0.4, 0.5], [0.2, 0.5]],
                ),
            )
            logger.info("Fired object_detected event")

    # ─── ObjectManipulation ───────────────────────────────────

    @component("ObjectManipulation", bind_required=True)
    class ObjectManipulation:

        @query("component_status")
        async def status(self):
            return results.status("BUSY" if self.parent._arm_busy else "READY")

        @query("gripper_state")
        async def gripper_state(self):
            return results.gripper_state("open")

        @query("current_grasped_object")
        async def current_grasped_object(self):
            return results.current_grasped_object("")

        @invoke("execute")
        async def execute(self, parameters):
            if self.parent._arm_busy:
                return InvokeResponse(return_code=ReturnCode.ERROR, command_id="")
            command = parameters[0].value if parameters else "unknown"
            logger.info("Manipulation: %s", command)
            self.parent._arm_busy = True
            return InvokeResponse(return_code=ReturnCode.OK, command_id="cmd-manip")

        @invoke("stop")
        async def stop(self, parameters):
            self.parent._arm_busy = False
            return InvokeResponse(return_code=ReturnCode.OK, command_id="")

        @subscribe("manipulation_complete")
        async def on_complete(self):
            # Fire a manipulation_complete event after 4 seconds.
            loop = asyncio.get_event_loop()
            loop.create_task(self._fire_complete())

        async def _fire_complete(self):
            await asyncio.sleep(4.0)
            self.parent._arm_busy = False
            self.parent.emit(  # type: ignore[attr-defined]
                "ObjectManipulation",
                "manipulation_complete",
                results.manipulation_complete(success=True, detail="grasp succeeded"),
            )
            logger.info("Fired manipulation_complete event")


def main() -> None:
    """Entry point: load config, create mock adapter, run framework."""
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Mock OpenRoIS adapter")
    parser.add_argument(
        "--config",
        default="openrois-profile.yaml",
        help="Path to the profile YAML file (default: openrois-profile.yaml)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    adapter = MockAdapter(config)
    framework = AdapterFramework(adapter, config)
    framework.run()


if __name__ == "__main__":
    main()
