"""Stream C: the behavior that closes CP1 to CP3, one group of tests per numbered item.

Each test is named after the item of the Stream E brief it guards, in the OpenRoIS First
Release document: item 1 connect gating, item 2 binds, item 3 component_status, item 4
command ids, item 5 branches, item 6 timeout, item 7 set_parameter, item 8 events, item 9
the error channel, item 10 streaming, item 11 SystemInformation, item 12 unknown
command types and item 13 get_profile.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components import AUDIO_STREAMING_URN, VIDEO_STREAMING_PROFILE
from openrois.interfaces.condition import COMPONENT_REF, all_of, eq, like
from openrois.interfaces.profiles import CommandMessageProfile, ComponentFunction

from openrois.engine import Engine
from tests._support import (
    ARM_PROFILE,
    Arm,
    EngineWatch,
    FakeChild,
    Gateway,
    Gripper,
    Lamp,
    LinkedDetection,
    LinkedNavigation,
    Microphone,
    Navigation,
    Peer,
    PersonDetection,
    RobotLink,
    RpcClient,
    Watcher,
    branches,
    command_ids,
    start_adapter,
    unit,
    wait_until,
)

NAV = "robot/navigation"
GRIP = "robot/gripper"
EYES = "robot/eyes"
WATCH = "robot/watcher"
LAMP = "robot/lamp"


@dataclass
class Robot:
    """An engine with its local components, started, and a connected client session."""

    engine: Engine
    navigation: Navigation
    gripper: Gripper
    watcher: Watcher
    client: Peer


@pytest.fixture
async def robot() -> AsyncIterator[Robot]:
    engine = Engine("robot")
    navigation = Navigation()
    gripper = Gripper()
    watcher = Watcher()
    engine.add_component("navigation", navigation)
    engine.add_component("gripper", gripper)
    engine.add_component("eyes", PersonDetection())
    engine.add_component("watcher", watcher)
    engine.add_component("lamp", Lamp())
    await engine.start()
    try:
        yield Robot(engine, navigation, gripper, watcher, await Peer.connected(engine))
    finally:
        await engine.stop()


async def bind(peer: Peer, *refs: str) -> Peer:
    for ref in refs:
        result = await peer.call("rois.command.bind", component_ref=ref)
        assert result["return_code"] == "OK", (ref, result)
    return peer


async def status(peer: Peer, ref: str) -> str:
    result = await peer.call(
        "rois.query.query", query_type="component_status", condition=eq(COMPONENT_REF, ref)
    )
    assert result["return_code"] == "OK", result
    value: str = result["results"][0]["value"]
    return value


def set_parameter(name: str, value: str) -> dict[str, str]:
    return {"name": name, "data_type_ref": "", "value": value}


# -- Item 1: connect gating ----------------------------------------------------------------


async def test_item_1_every_request_before_connect_is_answered_error(robot: Robot) -> None:
    newcomer = Peer(robot.engine)
    for method, params in [
        ("rois.system.get_profile", {"condition": ""}),
        ("rois.command.search", {"condition": ""}),
        ("rois.command.bind", {"component_ref": NAV}),
        ("rois.query.query", {"query_type": "width", "condition": ""}),
        ("rois.event.subscribe", {"event_type": "person_detected", "condition": ""}),
        ("rois.system.disconnect", {}),
    ]:
        result = await newcomer.call(method, **params)
        assert result["return_code"] == "ERROR", method
    assert (await newcomer.call("rois.system.connect"))["return_code"] == "OK"
    searched = await newcomer.call("rois.command.search", condition="")
    assert searched["return_code"] == "OK"


async def test_item_1_a_trusted_session_connects_too(robot: Robot) -> None:
    parent = Peer(robot.engine, trusted=True)
    result = await parent.call("rois.command.search", condition="")
    assert result["return_code"] == "ERROR"


async def test_item_1_requests_after_disconnect_are_answered_error(robot: Robot) -> None:
    assert (await robot.client.call("rois.system.disconnect"))["return_code"] == "OK"
    result = await robot.client.call("rois.command.search", condition="")
    assert result["return_code"] == "ERROR"
    assert (await robot.client.call("rois.system.connect"))["return_code"] == "OK"
    assert (await robot.client.call("rois.command.search", condition=""))["return_code"] == "OK"


async def test_item_1_disconnect_releases_binds_and_subscriptions_and_aborts_sequences(
    robot: Robot,
) -> None:
    client = await bind(robot.client, NAV, GRIP)
    other = await bind(await Peer.connected(robot.engine), EYES)
    await client.call(
        "rois.event.subscribe", event_type="reached_target", condition=eq(COMPONENT_REF, NAV)
    )
    start, grip = await client.execute(unit(NAV, "start"), unit(GRIP, "grip", force="1.0"))
    await asyncio.sleep(0.02)
    assert (await client.call("rois.system.disconnect"))["return_code"] == "OK"
    # The running start ends at once, its backend halted, and the grip never runs.
    await wait_until(lambda: robot.navigation.stops == 1)
    await asyncio.sleep(0.02)
    assert robot.gripper.forces == []
    assert not robot.engine._local._subscriptions
    # The session is gone, so nothing more reaches it.
    assert client.status_of(start) is None
    assert client.status_of(grip) is None
    # Its binds are free, and the other session keeps its own.
    taken = await Peer.connected(robot.engine)
    assert (await taken.call("rois.command.bind", component_ref=NAV))["return_code"] == "OK"
    kept = await other.call("rois.command.execute", command_unit_list=[unit(EYES, "start")])
    assert kept["return_code"] == "OK"


async def test_item_1_a_child_engine_is_connected_before_discovery(gateway: Gateway) -> None:
    child = await FakeChild.connect(gateway)
    first = await child.request()
    assert first["method"] == "rois.system.connect"
    await child.reply(first, {"return_code": "OK"})
    second = await child.request()
    assert second["method"] == "rois.system.get_profile"


async def test_item_1_aborting_a_command_in_a_child_sends_stop_then_release(
    gateway: Gateway,
) -> None:
    child = await FakeChild.connect(gateway)
    profile = ARM_PROFILE.model_copy(update={"command_profiles": [
        CommandMessageProfile(name="start"),
        CommandMessageProfile(name="stop"),
    ]})
    await child.answer_profile("cell", refs=["cell/arm"], profile=profile)
    await wait_until(lambda: "cell" in gateway.engine.child_engine_ids())
    client = await RpcClient.connect(gateway.url)
    try:
        assert (await client.call("rois.command.bind", component_ref="cell/arm"))[
            "return_code"
        ] == "OK"
        [start] = await client.execute(unit("cell/arm", "start"))
        forwarded = await child.request()
        assert forwarded["method"] == "rois.command.execute"
        assert forwarded["params"]["command_unit_list"][0]["command_id"] == start
        await child.reply(forwarded, {"return_code": "OK"})
        await client.call("rois.system.disconnect")
        stop = await child.request()
        assert stop["method"] == "rois.command.execute"
        [stop_unit] = stop["params"]["command_unit_list"]
        assert (stop_unit["component_ref"], stop_unit["command_type"]) == ("cell/arm", "stop")
        await child.reply(stop, {"return_code": "OK"})
        release = await child.request()
        assert release["method"] == "rois.command.release"
        assert release["params"] == {"component_ref": "cell/arm"}
    finally:
        await client.close()


async def test_item_1_disconnect_through_a_gateway_aborts_the_adapter_command(
    gateway: Gateway,
) -> None:
    adapter = await start_adapter(gateway.url, gateway)
    navigation = adapter.components["navigation"]
    assert isinstance(navigation, Navigation)
    client = await RpcClient.connect(gateway.url)
    try:
        await client.call("rois.command.bind", component_ref="robot/navigation")
        [start] = await client.execute(unit("robot/navigation", "start"))
        await asyncio.sleep(0.05)
        await client.call("rois.system.disconnect")
        await wait_until(lambda: navigation.stops >= 1)
        await wait_until(
            lambda: adapter.engine._commands[start].status is not None, timeout=2.0
        )
        assert adapter.engine._commands[start].status == "ABORT"
    finally:
        await client.close()
        await adapter.stop()


async def test_item_1_one_clients_disconnect_never_aborts_anothers_commands_in_a_child(
    gateway: Gateway,
) -> None:
    watcher = Watcher()
    adapter = await start_adapter(gateway.url, gateway, components={"watcher": watcher})
    first = await RpcClient.connect(gateway.url)
    second = await RpcClient.connect(gateway.url)
    try:
        for client in (first, second):
            await client.call("rois.command.bind", component_ref="robot/watcher")
        [mine] = await first.execute(unit("robot/watcher", "watch"))
        [theirs] = await second.execute(unit("robot/watcher", "watch"))
        await wait_until(lambda: watcher.watching == 2)
        # The second client still holds the shared sensor, so the gateway only stops
        # waiting for the first client's command, which runs on in the adapter.
        await first.call("rois.system.disconnect")
        await asyncio.sleep(0.1)
        assert watcher.watching == 2
        assert second.sent("rois.command.completed") == []
        # The last holder's release halts what still runs on the component.
        await second.call("rois.command.release", component_ref="robot/watcher")
        assert await second.completed(theirs) == "ABORT"
        await wait_until(lambda: watcher.watching == 0)
        assert first.sent("rois.command.completed") == []
        assert mine
    finally:
        await first.close()
        await second.close()
        await adapter.stop()


# -- Item 2: binds -----------------------------------------------------------------------


async def test_item_2_every_command_operation_needs_a_bind_on_every_component(
    robot: Robot,
) -> None:
    client = robot.client
    unbound = await client.call("rois.command.execute", command_unit_list=[unit(EYES, "start")])
    assert unbound["return_code"] == "ERROR"
    assert unbound["command_unit_list"] == []
    got = await client.call("rois.command.get_parameter", component_ref=NAV)
    assert got["return_code"] == "ERROR"
    changed = await client.call(
        "rois.command.set_parameter",
        component_ref=NAV,
        parameters=[set_parameter("time_limit", "5")],
    )
    assert changed["return_code"] == "ERROR"
    await bind(client, EYES, NAV)
    assert (await client.call("rois.command.get_parameter", component_ref=NAV))[
        "return_code"
    ] == "OK"
    [started] = await client.execute(unit(EYES, "start"))
    assert await client.completed(started) == "OK"


async def test_item_2_execute_refuses_a_sequence_with_an_unbound_component_before_it_runs(
    robot: Robot,
) -> None:
    await bind(robot.client, GRIP)
    result = await robot.client.call(
        "rois.command.execute",
        command_unit_list=[unit(GRIP, "grip", force="1.0"), unit(NAV, "start")],
    )
    assert result["return_code"] == "ERROR"
    await asyncio.sleep(0.02)
    assert robot.gripper.forces == []


async def test_item_2_an_actuation_component_takes_one_bind_at_a_time(robot: Robot) -> None:
    await bind(robot.client, NAV)
    other = await Peer.connected(robot.engine)
    refused = await other.call("rois.command.bind", component_ref=NAV)
    assert refused["return_code"] == "OUT_OF_RESOURCES"
    # Binding again from the holder is no error.
    assert (await robot.client.call("rois.command.bind", component_ref=NAV))[
        "return_code"
    ] == "OK"


async def test_item_2_sensing_and_unclassified_components_take_one_bind_per_session(
    robot: Robot,
) -> None:
    others = [await Peer.connected(robot.engine) for _ in range(2)]
    for peer in [robot.client, *others]:
        await bind(peer, EYES, WATCH, LAMP)
    for peer in [robot.client, *others]:
        [blink] = await peer.execute(unit(LAMP, "blink"))
        assert await peer.completed(blink) == "OK"


async def test_item_2_bind_any_reserves_a_component_the_session_can_bind(robot: Robot) -> None:
    other = await bind(await Peer.connected(robot.engine), NAV)
    taken = await other.call("rois.command.bind_any", condition=eq(COMPONENT_REF, NAV))
    assert taken == {"return_code": "OK", "component_ref": NAV}
    refused = await robot.client.call("rois.command.bind_any", condition=eq(COMPONENT_REF, NAV))
    assert refused["return_code"] == "OUT_OF_RESOURCES"
    shared = await robot.client.call("rois.command.bind_any", condition=eq(COMPONENT_REF, EYES))
    assert shared == {"return_code": "OK", "component_ref": EYES}


async def test_item_2_release_drops_the_callers_bind_and_aborts_its_commands_there(
    robot: Robot,
) -> None:
    client = await bind(robot.client, NAV, WATCH)
    other = await bind(await Peer.connected(robot.engine), WATCH)
    [start] = await client.execute(unit(NAV, "start"))
    [mine] = await client.execute(unit(WATCH, "watch"))
    [theirs] = await other.execute(unit(WATCH, "watch"))
    await wait_until(lambda: robot.watcher.watching == 2)
    released = await client.call("rois.command.release", component_ref=WATCH)
    assert released["return_code"] == "OK"
    assert await client.completed(mine) == "ABORT"
    # The other session's command and bind on the shared sensor are untouched, and so
    # is the caller's command on the component it did not release.
    await asyncio.sleep(0.02)
    assert other.status_of(theirs) is None
    assert client.status_of(start) is None
    assert robot.watcher.watching == 1
    released = await client.call("rois.command.release", component_ref=NAV)
    assert await client.completed(start) == "ABORT"
    assert robot.navigation.stops == 1
    robot.watcher.done.set()
    assert await other.completed(theirs) == "OK"
    # Without its bind, the caller may not command the sensor any more.
    again = await client.call("rois.command.execute", command_unit_list=[unit(WATCH, "watch")])
    assert again["return_code"] == "ERROR"


async def test_item_2_the_gateway_checks_the_binds_for_its_child_engines(
    gateway: Gateway,
) -> None:
    adapter = await start_adapter(
        gateway.url, gateway, components={"eyes": PersonDetection(), "lamp": Lamp()}
    )
    client = await RpcClient.connect(gateway.url)
    try:
        unbound = await client.call(
            "rois.command.execute", command_unit_list=[unit("robot/eyes", "start")]
        )
        assert unbound["return_code"] == "ERROR"
        await client.call("rois.command.bind", component_ref="robot/eyes")
        [started] = await client.execute(unit("robot/eyes", "start"))
        assert await client.completed(started) == "OK"
    finally:
        await client.close()
        await adapter.stop()


# -- Item 3: component_status ------------------------------------------------------------


async def test_item_3_component_status_is_answered_for_the_asking_session(
    robot: Robot,
) -> None:
    other = await Peer.connected(robot.engine)
    assert await status(robot.client, NAV) == "READY"
    await bind(robot.client, NAV)
    assert await status(robot.client, NAV) == "READY"
    assert await status(other, NAV) == "BUSY"
    # A shared component is never BUSY through binds.
    await bind(robot.client, EYES)
    assert await status(other, EYES) == "READY"
    await robot.client.call("rois.command.release", component_ref=NAV)
    assert await status(other, NAV) == "READY"


async def test_item_3_busy_is_not_running(robot: Robot) -> None:
    client = await bind(robot.client, NAV)
    await client.execute(unit(NAV, "start"))
    await asyncio.sleep(0.02)
    assert await status(client, NAV) == "READY"


async def test_item_3_a_component_is_uninitialized_until_its_resources_are_open() -> None:
    gate = asyncio.Event()
    link = RobotLink(gate=gate)
    engine = Engine("robot")
    engine.add_component("navigation", LinkedNavigation(link))
    client = await Peer.connected(engine)
    starting = asyncio.create_task(engine.start())
    try:
        await asyncio.sleep(0.02)
        assert await status(client, NAV) == "UNINITIALIZED"
        gate.set()
        await starting
        assert await status(client, NAV) == "READY"
    finally:
        await engine.stop()


async def test_item_3_raised_error_above_warning_above_the_lifecycle(robot: Robot) -> None:
    other = await Peer.connected(robot.engine)
    await bind(robot.client, NAV)
    robot.navigation.raise_status(ComponentStatus.WARNING, "The battery is low.")
    assert await status(robot.client, NAV) == "WARNING"
    assert await status(other, NAV) == "WARNING"
    robot.navigation.clear_status()
    assert await status(other, NAV) == "BUSY"
    robot.navigation.raise_status(ComponentStatus.ERROR, "The motor driver is gone.")
    assert await status(other, NAV) == "ERROR"


async def test_item_3_a_resource_status_reaches_every_component_that_uses_it() -> None:
    link = RobotLink()
    engine = Engine("robot")
    engine.add_component("navigation", LinkedNavigation(link))
    engine.add_component("eyes", LinkedDetection(link))
    engine.add_component("spare", Navigation())
    await engine.start()
    try:
        client = await Peer.connected(engine)
        assert link.opened == 1
        link.raise_status(ComponentStatus.WARNING, "The robot is not answering.")
        assert await status(client, NAV) == "WARNING"
        assert await status(client, EYES) == "WARNING"
        assert await status(client, "robot/spare") == "READY"
        link.clear_status()
        assert await status(client, NAV) == "READY"
    finally:
        await engine.stop()
    assert link.closed == 1


async def test_item_3_a_resource_that_cannot_open_fails_its_components() -> None:
    link = RobotLink(fail=True)
    navigation = LinkedNavigation(link)
    engine = Engine("robot")
    engine.add_component("navigation", navigation)
    await engine.start()
    try:
        client = await Peer.connected(engine)
        assert await status(client, NAV) == "ERROR"
        assert not navigation.connected
    finally:
        await engine.stop()


async def test_item_3_component_status_through_a_gateway_is_for_the_asking_client(
    gateway: Gateway,
) -> None:
    adapter = await start_adapter(gateway.url, gateway)
    holder = await RpcClient.connect(gateway.url)
    other = await RpcClient.connect(gateway.url)
    try:
        await holder.call("rois.command.bind", component_ref="robot/navigation")
        for client, expected in [(holder, "READY"), (other, "BUSY")]:
            result = await client.call(
                "rois.query.query",
                query_type="component_status",
                condition=eq(COMPONENT_REF, "robot/navigation"),
            )
            assert result["results"][0]["value"] == expected
    finally:
        await holder.close()
        await other.close()
        await adapter.stop()


# -- Item 4: command ids -----------------------------------------------------------------


async def test_item_4_the_engine_assigns_every_command_id(robot: Robot) -> None:
    await bind(robot.client, GRIP)
    named = unit(GRIP, "grip", force="1.0") | {"command_id": "mine"}
    result = await robot.client.call(
        "rois.command.execute",
        command_unit_list=[named, branches([unit(GRIP, "grip", force="2.0")])],
    )
    assert result["return_code"] == "OK"
    first, second = command_ids(result)
    assert first != "mine"
    assert first.startswith("robot/cmd-")
    assert second.startswith("robot/cmd-")
    assert result["command_unit_list"][0]["component_ref"] == GRIP
    assert await robot.client.completed(first) == "OK"
    assert await robot.client.completed(second) == "OK"
    assert robot.client.status_of("mine") is None
    detail = await robot.client.call(
        "rois.command.get_command_result", command_id=first, condition=""
    )
    assert detail["results"] == [{"name": "held", "data_type_ref": "bool", "value": "true"}]


async def test_item_4_a_trusted_parent_names_the_ids_and_the_child_reuses_them(
    robot: Robot,
) -> None:
    parent = await Peer.connected(robot.engine, trusted=True)
    result = await parent.call(
        "rois.command.execute",
        command_unit_list=[unit(GRIP, "grip", force="1.0") | {"command_id": "gateway/cmd-7"}],
    )
    assert command_ids(result) == ["gateway/cmd-7"]
    assert await parent.completed("gateway/cmd-7") == "OK"
    unnamed = await parent.call(
        "rois.command.execute", command_unit_list=[unit(GRIP, "grip", force="1.0")]
    )
    assert unnamed["return_code"] == "BAD_PARAMETER"


async def test_item_4_the_gateway_assigns_the_ids_and_the_adapter_reuses_them(
    gateway: Gateway,
) -> None:
    adapter = await start_adapter(gateway.url, gateway, components={"gripper": Gripper()})
    client = await RpcClient.connect(gateway.url)
    try:
        await client.call("rois.command.bind", component_ref="robot/gripper")
        [grip] = await client.execute(unit("robot/gripper", "grip", force="1.0"))
        assert grip.startswith("gateway/cmd-")
        assert await client.completed(grip) == "OK"
        assert grip in adapter.engine._commands
    finally:
        await client.close()
        await adapter.stop()


# -- Item 5: branches --------------------------------------------------------------------


async def test_item_5_branches_run_in_parallel_and_each_branch_in_order(robot: Robot) -> None:
    client = await bind(robot.client, NAV, GRIP)
    start, after_start, alone, last = await client.execute(
        branches(
            [unit(NAV, "start"), unit(GRIP, "grip", force="1.0")],
            [unit(GRIP, "grip", force="2.0")],
        ),
        unit(GRIP, "grip", force="3.0"),
    )
    assert await client.completed(alone) == "OK"
    await asyncio.sleep(0.05)
    assert robot.gripper.forces == [2.0]
    robot.navigation.arrive.set()
    assert await client.completed(last) == "OK"
    assert robot.gripper.forces == [2.0, 1.0, 3.0]
    assert client.status_of(start) == "OK"
    assert client.status_of(after_start) == "OK"


async def test_item_5_a_flat_command_list_is_one_branch_per_command(robot: Robot) -> None:
    client = await bind(robot.client, NAV, GRIP)
    start, grip = await client.execute(
        {"command_list": [unit(NAV, "start"), unit(GRIP, "grip", force="1.0")]}
    )
    assert await client.completed(grip) == "OK"
    assert client.status_of(start) is None
    robot.navigation.arrive.set()
    assert await client.completed(start) == "OK"


async def test_item_5_a_failure_aborts_the_rest_of_its_branch_and_the_later_units(
    robot: Robot,
) -> None:
    client = await bind(robot.client, NAV, GRIP)
    # A started navigation runs its failing suspend handler.
    await client.execute(unit(NAV, "start"))
    failed, skipped, other, later = await client.execute(
        branches(
            [unit(NAV, "suspend"), unit(GRIP, "grip", force="1.0")],
            [unit(GRIP, "grip", force="2.0")],
        ),
        unit(GRIP, "grip", force="3.0"),
    )
    assert await client.completed(failed) == "OUT_OF_RESOURCES"
    assert await client.completed(skipped) == "ABORT"
    assert await client.completed(other) == "OK"
    assert await client.completed(later) == "ABORT"
    assert robot.gripper.forces == [2.0]


# -- Item 6: timeout ---------------------------------------------------------------------


async def test_item_6_a_command_that_started_is_not_timed_out(robot: Robot) -> None:
    client = await bind(robot.client, GRIP)
    [squeeze] = await client.execute(unit(GRIP, "squeeze"))
    await asyncio.sleep(0.15)
    # squeeze has a 50 ms timeout, which judges only whether it started.
    assert client.status_of(squeeze) is None


async def test_item_6_a_command_not_started_within_its_timeout_ends_with_timeout() -> None:
    engine = Engine("robot")
    arm = Arm()
    engine.add_component("arm", arm)
    await engine.start()
    try:
        client = await bind(await Peer.connected(engine), "robot/arm")
        [first] = await client.execute(unit("robot/arm", "start"))
        await wait_until(lambda: arm.starts == 1)
        # The second start waits for the first to unwind, 0.3 s, past its 50 ms.
        [second] = await client.execute(unit("robot/arm", "start"))
        assert await client.completed(first) == "ABORT"
        assert await client.completed(second) == "TIMEOUT"
        assert arm.starts == 1
    finally:
        await engine.stop()


async def test_item_6_a_child_that_does_not_start_a_command_in_time_times_it_out(
    gateway: Gateway,
) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("cell", refs=["cell/arm"], profile=ARM_PROFILE)
    await wait_until(lambda: "cell" in gateway.engine.child_engine_ids())
    client = await RpcClient.connect(gateway.url)
    try:
        await client.call("rois.command.bind", component_ref="cell/arm")
        loop = asyncio.get_running_loop()
        began = loop.time()
        [start] = await client.execute(unit("cell/arm", "start"))
        await child.request()  # The execute, which the child never answers.
        assert await client.completed(start) == "TIMEOUT"
        assert loop.time() - began < 0.4
    finally:
        await client.close()


# -- Item 7: set_parameter ---------------------------------------------------------------


async def test_item_7_set_parameter_applies_before_it_replies_then_completes(
    robot: Robot,
) -> None:
    client = await bind(robot.client, NAV)
    result = await client.call(
        "rois.command.set_parameter",
        component_ref=NAV,
        parameters=[set_parameter("time_limit", "30")],
    )
    assert result["return_code"] == "OK"
    assert robot.navigation.applied == [{"time_limit": 30}]
    assert client.sent("rois.command.completed") == []
    assert await client.completed(result["command_id"]) == "OK"
    stored = await client.call("rois.command.get_parameter", component_ref=NAV)
    assert {"name": "time_limit", "data_type_ref": "int", "value": "30"} in stored["parameters"]


async def test_item_7_through_a_gateway_the_reply_comes_after_the_values_apply(
    gateway: Gateway,
) -> None:
    adapter = await start_adapter(gateway.url, gateway)
    navigation = adapter.components["navigation"]
    assert isinstance(navigation, Navigation)
    client = await RpcClient.connect(gateway.url)
    try:
        await client.call("rois.command.bind", component_ref="robot/navigation")
        result = await client.call(
            "rois.command.set_parameter",
            component_ref="robot/navigation",
            parameters=[set_parameter("time_limit", "12")],
        )
        assert result["return_code"] == "OK"
        assert navigation.applied == [{"time_limit": 12}]
        assert await client.completed(result["command_id"]) == "OK"
        reply = next(i for i, m in enumerate(client.messages) if m.get("result") == result)
        completed = next(
            i
            for i, m in enumerate(client.messages)
            if m.get("method") == "rois.command.completed"
        )
        assert reply < completed
    finally:
        await client.close()
        await adapter.stop()


@pytest.mark.parametrize(
    "parameters",
    [
        [set_parameter("time_limit", "5"), set_parameter("speed", "3")],
        [set_parameter("available_encodings", "opus")],
    ],
    ids=["unknown", "read_only"],
)
async def test_item_7_an_unknown_or_read_only_parameter_is_bad_parameter(
    parameters: list[dict[str, str]],
) -> None:
    engine = Engine("robot")
    navigation = Navigation()
    engine.add_component("navigation", navigation)
    engine.add_component("microphone", Microphone())
    await engine.start()
    try:
        client = await bind(await Peer.connected(engine), NAV, "robot/microphone")
        ref = "robot/microphone" if parameters[0]["name"] == "available_encodings" else NAV
        result = await client.call(
            "rois.command.set_parameter", component_ref=ref, parameters=parameters
        )
        assert result["return_code"] == "BAD_PARAMETER"
        assert navigation.applied == []
        stored = await client.call("rois.command.get_parameter", component_ref=NAV)
        assert {"name": "time_limit", "data_type_ref": "int", "value": "0"} in stored[
            "parameters"
        ]
    finally:
        await engine.stop()


async def test_item_7_set_parameter_inside_execute_behaves_the_same() -> None:
    engine = Engine("robot")
    navigation = Navigation()
    engine.add_component("navigation", navigation)
    engine.add_component("microphone", Microphone())
    await engine.start()
    try:
        client = await bind(await Peer.connected(engine), NAV, "robot/microphone")
        [change] = await client.execute(unit(NAV, "set_parameter", time_limit="30"))
        assert await client.completed(change) == "OK"
        assert navigation.applied == [{"time_limit": 30}]
        read_only = await client.call(
            "rois.command.execute",
            command_unit_list=[unit("robot/microphone", "set_parameter", available_encodings="x")],
        )
        assert read_only["return_code"] == "BAD_PARAMETER"
        unknown = await client.call(
            "rois.command.execute", command_unit_list=[unit(NAV, "set_parameter", speed="3")]
        )
        assert unknown["return_code"] == "BAD_PARAMETER"
    finally:
        await engine.stop()


# -- Item 8: events ----------------------------------------------------------------------


async def test_item_8_a_repeated_subscribe_returns_the_existing_subscription(
    robot: Robot,
) -> None:
    condition = eq(COMPONENT_REF, NAV)
    first = await robot.client.call(
        "rois.event.subscribe", event_type="reached_target", condition=condition
    )
    again = await robot.client.call(
        "rois.event.subscribe", event_type="reached_target", condition=condition
    )
    assert again == first
    assert robot.navigation.subscribed == 1
    other = await Peer.connected(robot.engine)
    theirs = await other.call(
        "rois.event.subscribe", event_type="reached_target", condition=condition
    )
    assert theirs["subscribe_id"] != first["subscribe_id"]


async def test_item_8_unsubscribe_of_an_unknown_or_removed_id_is_ok(robot: Robot) -> None:
    subscribed = await robot.client.call(
        "rois.event.subscribe", event_type="reached_target", condition=eq(COMPONENT_REF, NAV)
    )
    subscribe_id = subscribed["subscribe_id"]
    for _ in range(2):
        result = await robot.client.call("rois.event.unsubscribe", subscribe_id=subscribe_id)
        assert result == {"return_code": "OK"}
    unknown = await robot.client.call("rois.event.unsubscribe", subscribe_id="robot/sub-999")
    assert unknown == {"return_code": "OK"}


# -- Item 9: the error channel -------------------------------------------------------------


async def test_item_9_a_raise_sends_notify_error_to_the_sessions_on_the_component(
    robot: Robot,
) -> None:
    holder = await bind(robot.client, NAV)
    watcher = await Peer.connected(robot.engine)
    await watcher.call(
        "rois.event.subscribe", event_type="reached_target", condition=eq(COMPONENT_REF, NAV)
    )
    parent = await Peer.connected(robot.engine, trusted=True)
    bystander = await Peer.connected(robot.engine)
    robot.navigation.raise_status(ComponentStatus.WARNING, "The battery is low.")
    await wait_until(lambda: len(holder.sent("rois.system.notify_error")) == 1)
    [error] = holder.sent("rois.system.notify_error")
    assert error["error_id"].startswith("robot/err-")
    assert error["error_type"] == "COMPONENT_INTERNAL_ERROR"
    assert watcher.sent("rois.system.notify_error") == [error]
    assert parent.sent("rois.system.notify_error") == [error]
    assert bystander.sent("rois.system.notify_error") == []
    detail = await holder.call(
        "rois.system.get_error_detail", error_id=error["error_id"], condition=""
    )
    assert detail["return_code"] == "OK"
    values = {r["name"]: r["value"] for r in detail["results"]}
    assert values["component_ref"] == NAV
    assert values["status"] == "WARNING"
    assert values["message"] == "The battery is low."
    assert values["time"]
    # A raise that does not change what the component reports is no new error.
    robot.navigation.raise_status(ComponentStatus.WARNING, "Still low.")
    await asyncio.sleep(0.02)
    assert len(holder.sent("rois.system.notify_error")) == 1
    # Clearing sends nothing, and the detail is gone.
    robot.navigation.clear_status()
    await asyncio.sleep(0.02)
    assert len(holder.sent("rois.system.notify_error")) == 1
    gone = await holder.call(
        "rois.system.get_error_detail", error_id=error["error_id"], condition=""
    )
    assert gone["return_code"] == "BAD_PARAMETER"


async def test_item_9_a_resource_raise_is_one_error_per_component() -> None:
    link = RobotLink()
    engine = Engine("robot")
    engine.add_component("navigation", LinkedNavigation(link))
    engine.add_component("eyes", LinkedDetection(link))
    await engine.start()
    try:
        parent = await Peer.connected(engine, trusted=True)
        link.raise_status(ComponentStatus.ERROR, "The robot is gone.")
        await wait_until(lambda: len(parent.sent("rois.system.notify_error")) == 2)
        errors = parent.sent("rois.system.notify_error")
        assert {e["error_type"] for e in errors} == {"COMPONENT_NOT_RESPONDING"}
        refs = set()
        for error in errors:
            detail = await parent.call(
                "rois.system.get_error_detail", error_id=error["error_id"], condition=""
            )
            refs |= {r["value"] for r in detail["results"] if r["name"] == "component_ref"}
        assert refs == {NAV, EYES}
    finally:
        await engine.stop()


async def test_item_9_an_engine_error_reaches_every_connected_session(robot: Robot) -> None:
    other = await Peer.connected(robot.engine)
    unconnected = Peer(robot.engine)
    robot.engine.raise_status(ComponentStatus.ERROR, "The map server is gone.")
    await wait_until(lambda: len(other.sent("rois.system.notify_error")) == 1)
    [error] = robot.client.sent("rois.system.notify_error")
    assert error["error_type"] == "ENGINE_INTERNAL_ERROR"
    assert error["error_id"].startswith("robot/err-")
    assert unconnected.notifications == []
    robot.engine.clear_status()


async def test_item_9_a_raised_error_refuses_commands_and_queries_and_holds_events(
    robot: Robot,
) -> None:
    client = await bind(robot.client, GRIP, NAV)
    await client.call(
        "rois.event.subscribe", event_type="reached_target", condition=eq(COMPONENT_REF, NAV)
    )
    robot.gripper.raise_status(ComponentStatus.ERROR, "The jaw is stuck.")
    robot.navigation.raise_status(ComponentStatus.ERROR, "The wheels are stuck.")
    await asyncio.sleep(0.01)
    [grip] = await client.execute(unit(GRIP, "grip", force="1.0"))
    assert await client.completed(grip) == "ERROR"
    assert robot.gripper.forces == []
    width = await client.call("rois.query.query", query_type="width", condition="")
    assert width["return_code"] == "ERROR"
    robot.navigation.emit("reached_target", target="dock", is_final_target=True)
    await asyncio.sleep(0.02)
    assert client.sent("rois.event.notify_event") == []
    robot.navigation.clear_status()
    robot.navigation.emit("reached_target", target="dock", is_final_target=True)
    await wait_until(lambda: len(client.sent("rois.event.notify_event")) == 1)


async def test_item_9_an_adapter_error_reaches_the_gateway_client(gateway: Gateway) -> None:
    adapter = await start_adapter(gateway.url, gateway)
    navigation = adapter.components["navigation"]
    client = await RpcClient.connect(gateway.url)
    bystander = await RpcClient.connect(gateway.url)
    try:
        await client.call("rois.command.bind", component_ref="robot/navigation")
        navigation.raise_status(ComponentStatus.ERROR, "The wheels are stuck.")
        error = await client.notification("rois.system.notify_error")
        assert error["error_id"].startswith("robot/err-")
        assert error["error_type"] == "COMPONENT_INTERNAL_ERROR"
        detail = await client.call(
            "rois.system.get_error_detail", error_id=error["error_id"], condition=""
        )
        values = {r["name"]: r["value"] for r in detail["results"]}
        assert values["component_ref"] == "robot/navigation"
        await asyncio.sleep(0.05)
        assert bystander.sent("rois.system.notify_error") == []
    finally:
        await client.close()
        await bystander.close()
        await adapter.stop()


# -- Item 10: streaming ------------------------------------------------------------------


@pytest.fixture
async def studio() -> AsyncIterator[tuple[Engine, Microphone, Peer]]:
    engine = Engine("studio")
    microphone = Microphone()
    engine.add_component("microphone", microphone)
    await engine.start()
    try:
        yield engine, microphone, await Peer.connected(engine)
    finally:
        await engine.stop()


async def test_item_10_a_query_takes_its_arguments_from_the_condition(
    studio: tuple[Engine, Microphone, Peer],
) -> None:
    _, microphone, client = studio
    result = await client.call(
        "rois.query.query", query_type="get_stream_status", condition=eq("stream_id", "a1")
    )
    assert result["return_code"] == "OK"
    assert result["results"] == [
        {"name": "status", "data_type_ref": "Stream_Status", "value": "STREAMING_RUNNING"}
    ]
    assert microphone.asked == ["a1"]
    unknown = await client.call(
        "rois.query.query", query_type="get_stream_status", condition=eq("track", "a1")
    )
    assert unknown["return_code"] == "BAD_PARAMETER"
    pattern = await client.call(
        "rois.query.query", query_type="get_stream_status", condition=like("stream_id", "a%")
    )
    assert pattern["return_code"] == "BAD_PARAMETER"


async def test_item_10_events_go_to_the_subscriptions_whose_arguments_match(
    studio: tuple[Engine, Microphone, Peer],
) -> None:
    _, microphone, client = studio

    async def subscribe(condition: str) -> str:
        result = await client.call(
            "rois.event.subscribe", event_type="notify_stream_status", condition=condition
        )
        assert result["return_code"] == "OK", result
        subscribe_id: str = result["subscribe_id"]
        return subscribe_id

    a1 = await subscribe(all_of(eq(COMPONENT_REF, "studio/microphone"), eq("stream_id", "a1")))
    a2 = await subscribe(eq("stream_id", "a2"))
    every = await subscribe("")
    assert microphone.watched == ["a1", "a2", None]

    def delivered() -> list[str]:
        return [e["subscribe_id"] for e in client.sent("rois.event.notify_event")]

    microphone.emit(
        "notify_stream_status",
        concerning={"stream_id": "a1"},
        timestamp="2026-10-16T00:00:00+00:00",
        status="STREAMING_RUNNING",
    )
    await wait_until(lambda: len(delivered()) == 2)
    assert sorted(delivered()) == sorted([a1, every])
    microphone.emit("notify_stream_status", status="STREAMING_NOT_RUNNING")
    await wait_until(lambda: len(delivered()) == 5)
    assert sorted(delivered()[2:]) == sorted([a1, a2, every])


async def test_item_10_the_streaming_profiles_are_served(
    studio: tuple[Engine, Microphone, Peer],
) -> None:
    _, _, client = studio
    profile = await client.call("rois.system.get_profile", condition="")
    served = profile["component_profiles"]["studio/microphone"]
    assert served["identifier"]["code"] == "AudioStreaming"
    assert served["function"] == "function"
    [query] = [q for q in served["query_profiles"] if q["name"] == "get_stream_status"]
    assert [a["name"] for a in query["arguments"]] == ["stream_id"]
    read_only = {p["name"] for p in served["parameter_profiles"] if p["read_only"]}
    assert read_only == {"available_encodings", "available_transports"}
    assert VIDEO_STREAMING_PROFILE.identifier.code == "VideoStreaming"
    assert AUDIO_STREAMING_URN.endswith("::AudioStreaming")


async def test_item_10_stream_methods_are_unknown_like_any_other(
    studio: tuple[Engine, Microphone, Peer],
) -> None:
    _, _, client = studio
    reply = await client.reply("rois.stream.connect_stream", {})
    assert reply["error"]["code"] == -32601


async def test_item_10_a_stream_query_reaches_an_adapter_through_the_gateway(
    gateway: Gateway,
) -> None:
    microphone = Microphone()
    adapter = await start_adapter(gateway.url, gateway, components={"microphone": microphone})
    client = await RpcClient.connect(gateway.url)
    try:
        result = await client.call(
            "rois.query.query", query_type="get_stream_status", condition=eq("stream_id", "v9")
        )
        assert result["return_code"] == "OK"
        assert microphone.asked == ["v9"]
    finally:
        await client.close()
        await adapter.stop()


# -- Item 11: SystemInformation ------------------------------------------------------------


async def test_item_11_engine_status_follows_the_engine_status() -> None:
    engine = Engine("robot")
    engine.add_component("system_info", EngineWatch())
    await engine.start()
    try:
        client = await Peer.connected(engine)

        async def engine_status() -> str:
            result = await client.call("rois.query.query", query_type="engine_status", condition="")
            values: dict[str, str] = {r["name"]: r["value"] for r in result["results"]}
            return values["status"]

        assert await engine_status() == "READY"
        engine.raise_status(ComponentStatus.WARNING, "The map is stale.")
        assert await engine_status() == "WARNING"
        engine.clear_status()
        assert await engine_status() == "READY"
        component_status = await client.call(
            "rois.query.query", query_type="component_status", condition=""
        )
        assert component_status["return_code"] == "UNSUPPORTED"
    finally:
        await engine.stop()


# -- Item 12: unknown command types --------------------------------------------------------


async def test_item_12_an_unknown_command_type_is_unsupported(robot: Robot) -> None:
    await bind(robot.client, NAV)
    result = await robot.client.call(
        "rois.command.execute", command_unit_list=[unit(NAV, "dance")]
    )
    assert result["return_code"] == "UNSUPPORTED"
    # The type check comes before the bind check.
    other = await Peer.connected(robot.engine)
    unbound = await other.call("rois.command.execute", command_unit_list=[unit(NAV, "dance")])
    assert unbound["return_code"] == "UNSUPPORTED"


# -- Item 13: get_profile ----------------------------------------------------------------


async def test_item_13_get_profile_answers_the_engine_profile_in_json(robot: Robot) -> None:
    result: Mapping[str, Any] = await robot.client.call("rois.system.get_profile", condition="")
    assert result["return_code"] == "OK"
    assert result["profile"]["identifier"]["code"] == "robot"
    assert result["profile"]["component_ids"] == [NAV, GRIP, EYES, WATCH, LAMP]
    assert result["component_profiles"][NAV]["function"] == ComponentFunction.ACTUATION.value
