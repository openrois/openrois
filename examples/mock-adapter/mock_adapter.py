"""Mock adapter for testing the OpenRoIS middleware without a real robot.

Connects to the gateway, registers 4 components, and responds with
hardcoded data. Fires events on a timer to simulate robot activity.

Usage:
    python mock_adapter.py --config openrois-profile.yaml

OPENROIS_GATEWAY_URL, when set, overrides the profile's engine.gateway_url,
so the same profile works on a host and inside Docker Compose.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Coroutine
from typing import Any

from openrois.engine import Engine, WsClient, component_config, read_profile
from openrois.interfaces.contract import InvokeResponse
from openrois.interfaces.hri import ReturnCode
from openrois_components_core import (
    component,
    invoke,
    meta_from_decorators,
    query,
    results,
    subscribe,
)

logger = logging.getLogger(__name__)

# Timer tasks that fire events. asyncio keeps only weak references to tasks,
# so a task nobody holds could be collected before it fires.
_background_tasks: set[asyncio.Task[None]] = set()


def _in_background(coroutine: Coroutine[Any, Any, None]) -> None:
    """Run a coroutine as a task that lives until it finishes."""
    task = asyncio.create_task(coroutine)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _first_value(parameters: list[Any], default: str = "unknown") -> str:
    """The value of the first parameter, which arrives as a JSON object."""
    if not parameters:
        return default
    first = parameters[0]
    if isinstance(first, dict):
        return str(first.get("value", default))
    return str(first)


# ─── SystemInformation ───────────────────────────────────────

@component("SystemInformation")
class SystemInformation:

    def __init__(self, config: dict) -> None:
        pass

    @query("robot_position")
    async def robot_position(self):
        return results.position(x=3.2, y=1.8, theta=0.5)

    @query("battery_level")
    async def battery_level(self):
        return results.battery_level(percentage=85.5)

    @query("component_status")
    async def status(self):
        return results.status("READY")


# ─── Navigation ──────────────────────────────────────────────

@component("Navigation", function="actuation")
class Navigation:

    def __init__(self, config: dict) -> None:
        self._busy = False
        self._target = ""

    @query("waypoints")
    async def get_waypoints(self):
        return results.waypoints([
            {"id": "desk", "name": "desk", "x": 2.0, "y": 1.5, "theta": 0.0},
            {"id": "kitchen", "name": "kitchen", "x": 5.0, "y": 3.0, "theta": 1.57},
        ])

    @query("component_status")
    async def status(self):
        return results.status("BUSY" if self._busy else "READY")

    @invoke("execute")
    async def navigate(self, parameters):
        if self._busy:
            return InvokeResponse(return_code=ReturnCode.ERROR, command_id="")
        target = _first_value(parameters)
        logger.info("Navigate to: %s", target)
        self._busy = True
        self._target = target
        return InvokeResponse(return_code=ReturnCode.OK, command_id="cmd-nav")

    @invoke("stop")
    async def stop(self, parameters):
        self._busy = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("reached_target")
    async def on_reached(self):
        # Fire a reached_target event after 5 seconds.
        _in_background(self._fire_reached())

    async def _fire_reached(self):
        await asyncio.sleep(5.0)
        self._busy = False
        await self.parent.emit_async(  # type: ignore[attr-defined]
            "Navigation",
            "reached_target",
            results.reached_target(
                target=self._target, is_final_target=True,
            ),
        )
        logger.info("Fired reached_target event")


# ─── ObjectDetection ────────────────────────────────────────

@component("ObjectDetection", function="sensing")
class ObjectDetection:

    def __init__(self, config: dict) -> None:
        pass

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
        _in_background(self._fire_detected())

    async def _fire_detected(self):
        await asyncio.sleep(3.0)
        await self.parent.emit_async(  # type: ignore[attr-defined]
            "ObjectDetection",
            "object_detected",
            results.detection(
                object_id="2",
                object_class="bottle",
                bounding_box=[[0.2, 0.3], [0.4, 0.3], [0.4, 0.5], [0.2, 0.5]],
            ),
        )
        logger.info("Fired object_detected event")


# ─── ObjectManipulation ─────────────────────────────────────

@component("ObjectManipulation", function="actuation")
class ObjectManipulation:

    def __init__(self, config: dict) -> None:
        self._busy = False

    @query("component_status")
    async def status(self):
        return results.status("BUSY" if self._busy else "READY")

    @query("gripper_state")
    async def gripper_state(self):
        return results.gripper_state("open")

    @query("current_grasped_object")
    async def current_grasped_object(self):
        return results.current_grasped_object("")

    @invoke("execute")
    async def execute(self, parameters):
        if self._busy:
            return InvokeResponse(return_code=ReturnCode.ERROR, command_id="")
        command = _first_value(parameters)
        logger.info("Manipulation: %s", command)
        self._busy = True
        return InvokeResponse(return_code=ReturnCode.OK, command_id="cmd-manip")

    @invoke("stop")
    async def stop(self, parameters):
        self._busy = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("manipulation_complete")
    async def on_complete(self):
        # Fire a manipulation_complete event after 4 seconds.
        _in_background(self._fire_complete())

    async def _fire_complete(self):
        await asyncio.sleep(4.0)
        self._busy = False
        await self.parent.emit_async(  # type: ignore[attr-defined]
            "ObjectManipulation",
            "manipulation_complete",
            results.manipulation_complete(success=True, detail="grasp succeeded"),
        )
        logger.info("Fired manipulation_complete event")


# ─── Registration ────────────────────────────────────────────

COMPONENT_CLASSES = [
    SystemInformation,
    Navigation,
    ObjectDetection,
    ObjectManipulation,
]


def main() -> None:
    """Entry point: load profile, create engine, register components, run."""
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Mock OpenRoIS adapter")
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

    gateway_url = os.environ.get("OPENROIS_GATEWAY_URL") or profile["engine"]["gateway_url"]
    ws_client = WsClient(engine, gateway_url)
    ws_client.run()


if __name__ == "__main__":
    main()
