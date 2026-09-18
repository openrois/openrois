"""Mock adapter for testing the OpenRoIS middleware without a real robot.

Connects to the gateway, registers 5 components, and responds with
hardcoded data. Fires events on a timer to simulate robot activity.

Usage:
    python mock_adapter.py --config openrois-profile.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import ReturnCode
from openrois_components_core import (
    component,
    invoke,
    meta_from_decorators,
    query,
    results,
    subscribe,
)
from openrois_core import Engine, WsClient, component_config, read_profile

logger = logging.getLogger(__name__)


def _param(parameters: list, name: str, default: str = "") -> str:
    """Return the value of a named parameter.

    The engine passes parameters as plain dictionaries with the RoIS shape
    (name, data_type_ref, value). Typed Parameter objects are accepted too, so
    the same helper works for in-process tests.
    """
    for p in parameters or []:
        pname = p.get("name") if isinstance(p, dict) else getattr(p, "name", None)
        if pname == name:
            if isinstance(p, dict):
                return str(p.get("value", default))
            return str(getattr(p, "value", default))
    return default


# ─── SystemInformation ───────────────────────────────────────

@component("SystemInformation")
class SystemInformation:

    def __init__(self, config: dict) -> None:
        pass

    @query("robot_position")
    async def robot_position(self):
        return results.position(x=3.2, y=1.8, theta=0.5)

    @query("component_status")
    async def status(self):
        return results.status("READY")


# ─── Navigation ──────────────────────────────────────────────

@component(
    "Navigation",
    function="actuation",
    parameters=[{"name": "target_positions", "data_type_ref": "string[]", "default_value": "[]"}],
)
class Navigation:

    def __init__(self, config: dict) -> None:
        self._busy = False
        self._target = ""

    @query("component_status")
    async def status(self):
        return results.status("BUSY" if self._busy else "READY")

    @invoke("set_parameter")
    async def set_parameter(self, parameters):
        self._target = _param(parameters, "target_positions", self._target)
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("start")
    async def start(self, parameters):
        return await self.navigate(parameters)

    @invoke("suspend")
    async def suspend(self, parameters):
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("resume")
    async def resume(self, parameters):
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("execute")
    async def navigate(self, parameters):
        if self._busy:
            return InvokeResponse(return_code=ReturnCode.ERROR, command_id="")
        target = _param(parameters, "target_positions", self._target or "unknown")
        logger.info("Navigate to: %s", target)
        self._busy = True
        self._target = target
        # Simulate the drive: five seconds later the target is reached, the
        # event goes to subscribers, and the command completes for its caller.
        asyncio.get_running_loop().create_task(self._fire_reached())
        return InvokeResponse(return_code=ReturnCode.OK, command_id="cmd-nav")

    @invoke("stop")
    async def stop(self, parameters):
        self._busy = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("reached_target")
    async def on_reached(self):
        # Nothing to set up: navigate() emits the event when the drive ends.
        pass

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
        # The command that started this navigation is done: tell its caller.
        await self.parent.complete_async("cmd-nav", "OK")  # type: ignore[attr-defined]
        logger.info("Fired reached_target event and completed cmd-nav")


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
        loop = asyncio.get_event_loop()
        loop.create_task(self._fire_detected())

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
        command = _param(parameters, "command", "unknown")
        logger.info("Manipulation: %s", command)
        self._busy = True
        # Simulate the grasp: four seconds later the event fires and the
        # command completes.
        asyncio.get_running_loop().create_task(self._fire_complete())
        return InvokeResponse(return_code=ReturnCode.OK, command_id="cmd-manip")

    @invoke("stop")
    async def stop(self, parameters):
        self._busy = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("start")
    async def start(self, parameters):
        return await self.execute(parameters)

    @invoke("suspend")
    async def suspend(self, parameters):
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("resume")
    async def resume(self, parameters):
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("manipulation_complete")
    async def on_complete(self):
        # Nothing to set up: execute() emits the event when the grasp ends.
        pass

    async def _fire_complete(self):
        await asyncio.sleep(4.0)
        self._busy = False
        await self.parent.emit_async(  # type: ignore[attr-defined]
            "ObjectManipulation",
            "manipulation_complete",
            results.manipulation_complete(success=True, detail="grasp succeeded"),
        )
        await self.parent.complete_async("cmd-manip", "OK")  # type: ignore[attr-defined]
        logger.info("Fired manipulation_complete event and completed cmd-manip")


# ─── SpeechSynthesis ─────────────────────────────────────────

@component(
    "SpeechSynthesis",
    function="actuation",
    parameters=[{"name": "speech_text", "data_type_ref": "string", "default_value": ""}],
)
class SpeechSynthesis:
    """A robot voice: speaks by logging and completes when the speech would end."""

    def __init__(self, config: dict) -> None:
        self._text = ""
        self._speaking = False
        self._counter = 0

    @query("component_status")
    async def status(self):
        return results.status("BUSY" if self._speaking else "READY")

    @invoke("set_parameter")
    async def set_parameter(self, parameters):
        self._text = _param(parameters, "speech_text", self._text)
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("start")
    async def start(self, parameters):
        return await self.execute(parameters)

    @invoke("execute")
    async def execute(self, parameters):
        text = _param(parameters, "speech_text", self._text)
        if self._speaking:
            return InvokeResponse(return_code=ReturnCode.ERROR, command_id="")
        self._counter += 1
        command_id = f"say-{self._counter}"
        self._speaking = True
        logger.info("[robot] says: %s", text)
        asyncio.get_running_loop().create_task(self._finish(command_id, text))
        return InvokeResponse(return_code=ReturnCode.OK, command_id=command_id)

    async def _finish(self, command_id: str, text: str) -> None:
        await asyncio.sleep(max(0.2, len(text) * 0.05))
        self._speaking = False
        await self.parent.complete_async(command_id, "OK")  # type: ignore[attr-defined]

    @invoke("stop")
    async def stop(self, parameters):
        self._speaking = False
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("suspend")
    async def suspend(self, parameters):
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("resume")
    async def resume(self, parameters):
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")


# ─── Registration ────────────────────────────────────────────

COMPONENT_CLASSES = [
    SystemInformation,
    Navigation,
    ObjectDetection,
    ObjectManipulation,
    SpeechSynthesis,
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

    ws_client = WsClient(
        engine,
        profile["engine"]["gateway_url"],
        token=profile["engine"].get("token"),  # required when the gateway authenticates
    )
    ws_client.run()


if __name__ == "__main__":
    main()
