"""The RoIS_Common default: start, stop, suspend and resume on any component that serves them.

The rules are the ones of the OpenRoIS First Release document, questions 8 and 9. A
component is started from the moment a start begins until stop, or until that start ends
other than OK. On a component that is not started, suspend, resume and stop complete OK
and run no handler. While it is suspended, start and every other function command wait
in the engine, set_parameter applies at once, and its events are dropped. resume
releases both, and stop ends the suspension and aborts the commands it held. A handler
adds to the engine part and never replaces it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from openrois.components.core import (
    CommandFailed,
    Component,
    component,
    invoke,
    on_set_parameter,
    subscribe,
)
from openrois.interfaces.components import ROIS_COMMON_PROFILE, ROIS_COMMON_URN
from openrois.interfaces.condition import COMPONENT_REF, eq
from openrois.interfaces.profiles import (
    CommandMessageProfile,
    ComponentFunction,
    EventMessageProfile,
    HRIComponentProfile,
    ParameterProfile,
    RoISIdentifierType,
)
from openrois.interfaces.service import CompletedStatus

from openrois.engine import Engine
from tests._support import Gateway, Peer, RpcClient, start_adapter, unit, wait_until

CAMERA = "robot/camera"


def _parameter(name: str, code: str, default: str | None = None) -> ParameterProfile:
    return ParameterProfile(
        name=name, data_type_ref=RoISIdentifierType(code=code), default_value=default
    )


#: A sensing type that includes RoISCommon, with function commands of its own: wave ends
#: at once, record runs until the test lets it end, and snap must begin within 50 ms.
CAMERA_PROFILE = HRIComponentProfile(
    identifier=RoISIdentifierType(authority="OpenRoIS", code="Camera"),
    name="camera",
    function=ComponentFunction.SENSING,
    sub_component_profiles=[ROIS_COMMON_URN],
    command_profiles=[
        *ROIS_COMMON_PROFILE.command_profiles,
        CommandMessageProfile(name="wave"),
        CommandMessageProfile(name="record"),
        CommandMessageProfile(name="snap", timeout=50),
    ],
    query_profiles=list(ROIS_COMMON_PROFILE.query_profiles),
    event_profiles=[EventMessageProfile(name="snapped", results=[_parameter("count", "int")])],
    parameter_profiles=[_parameter("zoom", "int", "1")],
)


@component(CAMERA_PROFILE)
class Camera(Component):
    """A camera with no RoIS_Common handler: the engine's default answers all four."""

    def __init__(self) -> None:
        self.log: list[str] = []
        self.recorded = asyncio.Event()
        self.zooms: list[int] = []

    @invoke("wave")
    async def wave(self) -> None:
        self.log.append("wave")

    @invoke("record")
    async def record(self) -> None:
        self.log.append("record")
        await self.recorded.wait()

    @invoke("snap")
    async def snap(self) -> None:
        self.log.append("snap")

    @subscribe("snapped")
    async def snapped(self) -> None:
        return None

    @on_set_parameter
    async def apply(self, values: Mapping[str, Any]) -> None:
        self.zooms.append(values["zoom"])


@component(CAMERA_PROFILE)
class HandledCamera(Camera):
    """A camera that overrides the four RoIS_Common commands.

    Each handler logs its name. ``starting`` makes start run until the test sets it,
    ``fail_start`` and ``fail_suspend`` make those handlers fail, and ``suspending`` and
    ``resuming`` make suspend and resume wait until the test sets them.
    """

    def __init__(self) -> None:
        super().__init__()
        self.starting: asyncio.Event | None = None
        self.fail_start = False
        self.fail_suspend = False
        self.suspending: asyncio.Event | None = None
        self.resuming: asyncio.Event | None = None

    @invoke("start")
    async def start(self) -> None:
        self.log.append("start")
        if self.fail_start:
            raise CommandFailed(CompletedStatus.ERROR, "The lens cap is on.")
        if self.starting is not None:
            await self.starting.wait()

    @invoke("stop")
    async def stop(self) -> None:
        self.log.append("stop")

    @invoke("suspend")
    async def suspend(self) -> None:
        self.log.append("suspend")
        if self.suspending is not None:
            await self.suspending.wait()
        if self.fail_suspend:
            raise CommandFailed(CompletedStatus.OUT_OF_RESOURCES, "The buffer is full.")

    @invoke("resume")
    async def resume(self) -> None:
        self.log.append("resume")
        if self.resuming is not None:
            await self.resuming.wait()


@dataclass
class Robot:
    engine: Engine
    camera: Camera
    client: Peer

    async def run(self, command_type: str) -> str:
        """Execute one command, and return its id."""
        [command_id] = await self.client.execute(unit(CAMERA, command_type))
        return command_id

    async def ran(self, command_type: str) -> str:
        """Execute one command, wait for it to complete, and return its status."""
        return await self.client.completed(await self.run(command_type))

    async def suspended(self) -> None:
        """Start the camera and suspend it."""
        assert await self.ran("start") == "OK"
        assert await self.ran("suspend") == "OK"


async def _robot(camera: Camera) -> Robot:
    engine = Engine("robot")
    engine.add_component("camera", camera)
    await engine.start()
    client = await Peer.connected(engine)
    assert (await client.call("rois.command.bind", component_ref=CAMERA))["return_code"] == "OK"
    return Robot(engine, camera, client)


@pytest.fixture
async def robot() -> AsyncIterator[Robot]:
    started = await _robot(Camera())
    try:
        yield started
    finally:
        await started.engine.stop()


@pytest.fixture
async def handled() -> AsyncIterator[Robot]:
    started = await _robot(HandledCamera())
    try:
        yield started
    finally:
        await started.engine.stop()


def _camera(robot: Robot) -> HandledCamera:
    assert isinstance(robot.camera, HandledCamera)
    return robot.camera


async def _still_held(robot: Robot, command_id: str) -> None:
    await asyncio.sleep(0.05)
    assert robot.client.status_of(command_id) is None


# -- Defaults on a component that is not started -----------------------------------------


async def test_the_four_commands_are_served_without_handlers(robot: Robot) -> None:
    result = await robot.client.call("rois.system.get_profile", condition="")
    names = [c["name"] for c in result["component_profiles"][CAMERA]["command_profiles"]]
    assert names[:4] == ["start", "stop", "suspend", "resume"]


async def test_a_start_without_a_handler_completes_ok(robot: Robot) -> None:
    assert await robot.ran("start") == "OK"


@pytest.mark.parametrize("command_type", ["suspend", "resume", "stop"])
async def test_on_a_component_not_started_they_are_ok_and_run_no_handler(
    handled: Robot, command_type: str
) -> None:
    assert await handled.ran(command_type) == "OK"
    assert _camera(handled).log == []


async def test_a_start_that_fails_leaves_the_component_not_started(handled: Robot) -> None:
    _camera(handled).fail_start = True
    assert await handled.ran("start") == "ERROR"
    assert await handled.ran("suspend") == "OK"
    assert _camera(handled).log == ["start"]


async def test_a_start_replaced_by_a_new_start_leaves_it_started(handled: Robot) -> None:
    starting = _camera(handled).starting = asyncio.Event()
    first = await handled.run("start")
    await wait_until(lambda: _camera(handled).log == ["start"])
    second = await handled.run("start")
    assert await handled.client.completed(first) == "ABORT"
    starting.set()
    assert await handled.client.completed(second) == "OK"
    assert await handled.ran("suspend") == "OK"
    assert _camera(handled).log[-1] == "suspend"


async def test_stop_ends_started(handled: Robot) -> None:
    assert await handled.ran("start") == "OK"
    assert await handled.ran("stop") == "OK"
    assert await handled.ran("suspend") == "OK"
    assert _camera(handled).log == ["start", "stop"]


@component(CAMERA_PROFILE)
class StubbornCamera(HandledCamera):
    """A camera whose start, cancelled once, keeps waiting until it is cancelled again."""

    @invoke("start")
    async def start(self) -> None:
        self.log.append("start")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.log.append("unwinding")
            await asyncio.Event().wait()


async def test_a_second_stop_cancels_a_start_still_unwinding() -> None:
    robot = await _robot(StubbornCamera())
    try:
        start = await robot.run("start")
        await wait_until(lambda: robot.camera.log == ["start"])
        assert await robot.ran("stop") == "OK"
        await wait_until(lambda: robot.camera.log[-1:] == ["unwinding"])
        assert robot.client.status_of(start) is None
        assert await robot.ran("stop") == "OK"
        assert await robot.client.completed(start) == "ABORT"
    finally:
        await robot.engine.stop()


# -- What suspend holds ------------------------------------------------------------------


async def test_suspend_holds_later_commands_until_resume(robot: Robot) -> None:
    await robot.suspended()
    wave = await robot.run("wave")
    await _still_held(robot, wave)
    assert robot.camera.log == []
    assert await robot.ran("resume") == "OK"
    assert await robot.client.completed(wave) == "OK"
    assert robot.camera.log == ["wave"]


async def test_a_new_start_is_held_too(handled: Robot) -> None:
    await handled.suspended()
    start = await handled.run("start")
    await _still_held(handled, start)
    assert await handled.ran("resume") == "OK"
    assert await handled.client.completed(start) == "OK"
    assert _camera(handled).log == ["start", "suspend", "resume", "start"]


async def test_a_sequence_waits_at_its_next_command(robot: Robot) -> None:
    await robot.suspended()
    first, second = await robot.client.execute(unit(CAMERA, "wave"), unit(CAMERA, "wave"))
    await _still_held(robot, first)
    assert await robot.ran("resume") == "OK"
    assert await robot.client.completed(first) == "OK"
    assert await robot.client.completed(second) == "OK"


async def test_a_command_already_running_keeps_running(robot: Robot) -> None:
    assert await robot.ran("start") == "OK"
    record = await robot.run("record")
    await wait_until(lambda: robot.camera.log == ["record"])
    assert await robot.ran("suspend") == "OK"
    robot.camera.recorded.set()
    assert await robot.client.completed(record) == "OK"


async def test_set_parameter_applies_at_once_while_suspended(robot: Robot) -> None:
    await robot.suspended()
    result = await robot.client.call(
        "rois.command.set_parameter",
        component_ref=CAMERA,
        parameters=[{"name": "zoom", "data_type_ref": "int", "value": "2"}],
    )
    assert await robot.client.completed(result["command_id"]) == "OK"
    [in_sequence] = await robot.client.execute(unit(CAMERA, "set_parameter", zoom="3"))
    assert await robot.client.completed(in_sequence) == "OK"
    assert robot.camera.zooms == [2, 3]


async def test_a_held_command_past_its_timeout_times_out(robot: Robot) -> None:
    await robot.suspended()
    snap = await robot.run("snap")
    assert await robot.client.completed(snap) == "TIMEOUT"
    assert await robot.ran("resume") == "OK"
    await asyncio.sleep(0.02)
    assert robot.camera.log == []


async def test_events_are_dropped_while_suspended(robot: Robot) -> None:
    subscribed = await robot.client.call(
        "rois.event.subscribe", event_type="snapped", condition=eq(COMPONENT_REF, CAMERA)
    )
    assert subscribed["return_code"] == "OK"
    await robot.suspended()
    robot.camera.emit("snapped", count=1)
    await asyncio.sleep(0.02)
    assert robot.client.sent("rois.event.notify_event") == []
    assert await robot.ran("resume") == "OK"
    robot.camera.emit("snapped", count=2)
    await wait_until(lambda: len(robot.client.sent("rois.event.notify_event")) == 1)
    [event] = robot.client.sent("rois.event.notify_event")
    assert event["results"][0]["value"] == "2"


async def test_component_status_does_not_change_while_suspended(robot: Robot) -> None:
    await robot.suspended()
    result = await robot.client.call(
        "rois.query.query", query_type="component_status", condition=eq(COMPONENT_REF, CAMERA)
    )
    assert result["results"][0]["value"] == "READY"


# -- stop while suspended ----------------------------------------------------------------


async def test_stop_aborts_the_held_commands_and_ends_the_suspension(handled: Robot) -> None:
    await handled.suspended()
    wave = await handled.run("wave")
    await _still_held(handled, wave)
    assert await handled.ran("stop") == "OK"
    assert await handled.client.completed(wave) == "ABORT"
    # The camera is no longer started, so a suspend now is a no-op, and nothing is held.
    assert await handled.ran("suspend") == "OK"
    assert await handled.ran("wave") == "OK"
    assert _camera(handled).log == ["start", "suspend", "stop", "wave"]


# -- Handlers add to the engine part -----------------------------------------------------


async def test_the_suspend_handler_runs_after_the_hold(handled: Robot) -> None:
    camera = _camera(handled)
    camera.suspending = asyncio.Event()
    assert await handled.ran("start") == "OK"
    suspend = await handled.run("suspend")
    await wait_until(lambda: camera.log[-1:] == ["suspend"])
    wave = await handled.run("wave")
    await _still_held(handled, wave)
    camera.suspending.set()
    assert await handled.client.completed(suspend) == "OK"
    await _still_held(handled, wave)
    assert await handled.ran("resume") == "OK"
    assert await handled.client.completed(wave) == "OK"


async def test_the_resume_handler_runs_before_the_release(handled: Robot) -> None:
    camera = _camera(handled)
    camera.resuming = asyncio.Event()
    await handled.suspended()
    wave = await handled.run("wave")
    resume = await handled.run("resume")
    await wait_until(lambda: camera.log[-1:] == ["resume"])
    await _still_held(handled, wave)
    camera.resuming.set()
    assert await handled.client.completed(resume) == "OK"
    assert await handled.client.completed(wave) == "OK"
    assert camera.log == ["start", "suspend", "resume", "wave"]


async def test_a_failed_suspend_handler_lifts_the_hold(handled: Robot) -> None:
    _camera(handled).fail_suspend = True
    assert await handled.ran("start") == "OK"
    assert await handled.ran("suspend") == "OUT_OF_RESOURCES"
    assert await handled.ran("wave") == "OK"


# -- Through a gateway -------------------------------------------------------------------


async def test_through_a_gateway_the_adapter_holds() -> None:
    gateway = await Gateway.start()
    camera = Camera()
    adapter = await start_adapter(gateway.url, gateway, components={"camera": camera})
    client = await RpcClient.connect(gateway.url)
    try:
        assert (await client.call("rois.command.bind", component_ref=CAMERA))[
            "return_code"
        ] == "OK"
        for command_type in ("start", "suspend"):
            [command_id] = await client.execute(unit(CAMERA, command_type))
            assert await client.completed(command_id) == "OK"
        [wave] = await client.execute(unit(CAMERA, "wave"))
        await asyncio.sleep(0.05)
        assert camera.log == []
        [resume] = await client.execute(unit(CAMERA, "resume"))
        assert await client.completed(resume) == "OK"
        assert await client.completed(wave) == "OK"
        assert camera.log == ["wave"]
    finally:
        await client.close()
        await adapter.stop()
        await gateway.stop()
