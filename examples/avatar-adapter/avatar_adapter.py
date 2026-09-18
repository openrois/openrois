"""A virtual agent behind the same interfaces as a robot.

This adapter hosts a text-based avatar: it has no body and no camera, but it
answers the same RoIS components a robot does. SpeechSynthesis "speaks" by
logging the text and completing the command after a duration proportional to
its length, Reaction "performs" an expression the same way, and
SystemInformation reports a virtual position. An application that drives a
robot's SpeechSynthesis drives this one with the same calls; it cannot tell,
and does not need to know, which one is on the other side.

Usage:
    python avatar_adapter.py --config openrois-profile.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import Result, ReturnCode
from openrois_components_core import (
    component,
    invoke,
    meta_from_decorators,
    query,
    results,
)
from openrois_core import Engine, WsClient, component_config, read_profile

logger = logging.getLogger("avatar")

# Seconds of "speech" per character, so a longer sentence takes longer to complete.
SECONDS_PER_CHARACTER = 0.05


def _param(parameters: list, name: str, default: str = "") -> str:
    for p in parameters or []:
        pname = p.get("name") if isinstance(p, dict) else getattr(p, "name", None)
        if pname == name:
            if isinstance(p, dict):
                return str(p.get("value", default))
            return str(getattr(p, "value", default))
    return default


@component("SystemInformation")
class SystemInformation:
    """A virtual position: the avatar sits at the origin of its own world."""

    def __init__(self, config: dict) -> None:
        self._name = config.get("name", "avatar")

    @query("robot_position")
    async def robot_position(self):
        return results.position(x=0.0, y=0.0, theta=0.0)

    @query("engine_status")
    async def engine_status(self):
        return [Result(name="status", data_type_ref="string", value="READY")]

    @query("component_status")
    async def status(self):
        return results.status("READY")


@component(
    "SpeechSynthesis",
    function="actuation",
    parameters=[
        {"name": "speech_text", "data_type_ref": "string", "default_value": ""},
        {"name": "volume", "data_type_ref": "int", "default_value": "100"},
    ],
)
class SpeechSynthesis:
    """Speaks by logging. The command completes when the "speech" would end."""

    def __init__(self, config: dict) -> None:
        self._name = config.get("name", "avatar")
        self._text = ""
        self._volume = "100"
        self._speaking = False
        self._counter = 0

    @query("component_status")
    async def status(self):
        return results.status("BUSY" if self._speaking else "READY")

    @invoke("set_parameter")
    async def set_parameter(self, parameters):
        self._text = _param(parameters, "speech_text", self._text)
        self._volume = _param(parameters, "volume", self._volume)
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
        logger.info("[%s] says (volume %s): %s", self._name, self._volume, text)
        asyncio.get_running_loop().create_task(self._finish(command_id, text))
        return InvokeResponse(return_code=ReturnCode.OK, command_id=command_id)

    async def _finish(self, command_id: str, text: str) -> None:
        await asyncio.sleep(max(0.2, len(text) * SECONDS_PER_CHARACTER))
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


@component(
    "Reaction",
    function="actuation",
    parameters=[{"name": "reaction_ref", "data_type_ref": "string", "default_value": "neutral"}],
)
class Reaction:
    """Performs an expression by logging it: smile, nod, wave, and so on."""

    def __init__(self, config: dict) -> None:
        self._name = config.get("name", "avatar")
        self._reaction = "neutral"
        self._counter = 0

    @query("component_status")
    async def status(self):
        return results.status("READY")

    @query("get_parameter")
    async def get_parameter(self):
        return [Result(name="reaction_ref", data_type_ref="string", value=self._reaction)]

    @invoke("set_parameter")
    async def set_parameter(self, parameters):
        self._reaction = _param(parameters, "reaction_ref", self._reaction)
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("start")
    async def start(self, parameters):
        return await self.execute(parameters)

    @invoke("execute")
    async def execute(self, parameters):
        reaction = _param(parameters, "reaction_ref", self._reaction)
        self._counter += 1
        command_id = f"react-{self._counter}"
        logger.info("[%s] performs: %s", self._name, reaction)
        asyncio.get_running_loop().create_task(self._finish(command_id))
        return InvokeResponse(return_code=ReturnCode.OK, command_id=command_id)

    async def _finish(self, command_id: str) -> None:
        await asyncio.sleep(0.5)
        await self.parent.complete_async(command_id, "OK")  # type: ignore[attr-defined]

    @invoke("stop")
    async def stop(self, parameters):
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("suspend")
    async def suspend(self, parameters):
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("resume")
    async def resume(self, parameters):
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")


COMPONENT_CLASSES = [SystemInformation, SpeechSynthesis, Reaction]


def build_engine(profile: dict) -> Engine:
    """An engine with the avatar's components registered from a profile dict."""
    engine = Engine(
        engine_id=profile["engine"]["id"],
        platform=profile["engine"].get("platform", "avatar"),
    )
    for cls in COMPONENT_CLASSES:
        meta = meta_from_decorators(cls)
        engine.register_component(meta.ref, cls(component_config(profile, meta.ref)), meta)
    return engine


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Virtual agent adapter for OpenRoIS")
    parser.add_argument("--config", default="openrois-profile.yaml")
    args = parser.parse_args()
    profile = read_profile(args.config)
    engine = build_engine(profile)
    WsClient(
        engine,
        profile["engine"]["gateway_url"],
        token=profile["engine"].get("token"),
    ).run()


if __name__ == "__main__":
    main()
