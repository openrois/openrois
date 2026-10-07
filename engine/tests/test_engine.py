"""The engine on its own components: the method catalog, commands, parameters and events."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass

import pytest
from openrois.interfaces.components import NAVIGATION_URN
from openrois.interfaces.condition import COMPONENT_REF, COMPONENT_TYPE, eq

from openrois.engine import Engine
from tests._support import Gripper, Navigation, Peer, PersonDetection, unit, wait_until

NAV = "robot/navigation"
GRIP = "robot/gripper"
EYES = "robot/eyes"


@dataclass
class Robot:
    """An engine with three local components, started, and a client session."""

    engine: Engine
    navigation: Navigation
    gripper: Gripper
    client: Peer


@pytest.fixture
async def robot() -> AsyncIterator[Robot]:
    engine = Engine("robot")
    navigation = Navigation()
    gripper = Gripper()
    engine.add_component("navigation", navigation)
    engine.add_component("gripper", gripper)
    engine.add_component("eyes", PersonDetection())
    await engine.start()
    try:
        yield Robot(engine, navigation, gripper, Peer(engine))
    finally:
        await engine.stop()


async def bound(robot: Robot, *refs: str) -> Peer:
    """The client of a robot, holding the bindings of some components."""
    for ref in refs:
        assert (await robot.client.call("rois.command.bind", component_ref=ref))[
            "return_code"
        ] == "OK"
    return robot.client


async def execute(peer: Peer, *items: Mapping[str, object]) -> str:
    result = await peer.call("rois.command.execute", command_unit_list=list(items))
    return str(result["return_code"])


# -- Engine and components ---------------------------------------------------------------


@pytest.mark.parametrize("engine_id", ["", "lab/robot"])
def test_an_engine_id_is_non_empty_and_free_of_slashes(engine_id: str) -> None:
    with pytest.raises(ValueError, match="engine id"):
        Engine(engine_id)


def test_a_component_name_is_unique_and_free_of_slashes() -> None:
    engine = Engine("robot")
    assert engine.add_component("navigation", Navigation()) == NAV
    with pytest.raises(ValueError, match="already hosted"):
        engine.add_component("navigation", Navigation())
    with pytest.raises(ValueError, match="free of slashes"):
        engine.add_component("arm/left", Gripper())


async def test_start_connects_and_stop_disconnects_the_components() -> None:
    engine = Engine("robot")
    navigation = Navigation()
    engine.add_component("navigation", navigation)
    await engine.start()
    assert navigation.connected
    await engine.stop()
    assert not navigation.connected


# -- SystemIF and search -----------------------------------------------------------------


async def test_get_profile_lists_every_component_with_the_profile_it_serves(
    robot: Robot,
) -> None:
    result = await robot.client.call("rois.system.get_profile", condition="")
    assert result["profile"]["identifier"] == {
        "authority": "OpenRoIS",
        "code": "robot",
        "codebook_ref": "",
        "version": "",
    }
    assert result["profile"]["component_ids"] == [NAV, GRIP, EYES]
    navigation = result["component_profiles"][NAV]
    assert navigation["name"] == "navigation"
    assert [c["name"] for c in navigation["command_profiles"]] == [
        "start",
        "stop",
        "suspend",
        "resume",
    ]
    assert [q["name"] for q in navigation["query_profiles"]] == ["component_status"]
    eyes = result["component_profiles"][EYES]
    assert [c["name"] for c in eyes["command_profiles"]] == ["start", "stop"]


async def test_a_condition_selects_components(robot: Robot) -> None:
    by_type = await robot.client.call(
        "rois.command.search", condition=eq(COMPONENT_TYPE, NAVIGATION_URN)
    )
    assert by_type["component_ref_list"] == [NAV]
    profile = await robot.client.call("rois.system.get_profile", condition=eq(COMPONENT_REF, GRIP))
    assert profile["profile"]["component_ids"] == [GRIP]
    assert list(profile["component_profiles"]) == [GRIP]


async def test_a_condition_that_does_not_parse_is_bad_parameter(robot: Robot) -> None:
    for method in ("rois.command.search", "rois.system.get_profile", "rois.command.bind_any"):
        result = await robot.client.call(method, condition="component_ref == 'robot/x'")
        assert result["return_code"] == "BAD_PARAMETER", method


async def test_connect_answers_ok(robot: Robot) -> None:
    assert (await robot.client.call("rois.system.connect"))["return_code"] == "OK"


async def test_an_unknown_error_id_is_bad_parameter(robot: Robot) -> None:
    result = await robot.client.call(
        "rois.system.get_error_detail", error_id="robot/err-1", condition=""
    )
    assert result["return_code"] == "BAD_PARAMETER"


# -- Bindings ------------------------------------------------------------------------------


async def test_an_actuation_component_takes_commands_from_its_binding_only(
    robot: Robot,
) -> None:
    grip = unit(GRIP, "grip", "c1", force="1.0")
    assert await execute(robot.client, grip) == "OUT_OF_RESOURCES"
    await bound(robot, GRIP)
    assert await execute(robot.client, grip) == "OK"
    other = Peer(robot.engine)
    assert (await other.call("rois.command.bind", component_ref=GRIP))[
        "return_code"
    ] == "OUT_OF_RESOURCES"
    assert await execute(other, unit(GRIP, "grip", "c2", force="1.0")) == "OUT_OF_RESOURCES"


async def test_release_frees_the_component_for_another_session(robot: Robot) -> None:
    await bound(robot, GRIP)
    released = await robot.client.call("rois.command.release", component_ref=GRIP)
    assert released["return_code"] == "OK"
    other = Peer(robot.engine)
    assert (await other.call("rois.command.bind", component_ref=GRIP))["return_code"] == "OK"


async def test_bind_any_reserves_a_free_component_that_matches(robot: Robot) -> None:
    other = Peer(robot.engine)
    await other.call("rois.command.bind", component_ref=NAV)
    actuation = "component_ref LIKE 'robot/%'"
    result = await robot.client.call("rois.command.bind_any", condition=actuation)
    assert result == {"return_code": "OK", "component_ref": GRIP}
    taken = await robot.client.call("rois.command.bind_any", condition=eq(COMPONENT_REF, NAV))
    assert taken["return_code"] == "OUT_OF_RESOURCES"
    none = await robot.client.call("rois.command.bind_any", condition=eq(COMPONENT_REF, "x/y"))
    assert none["return_code"] == "UNSUPPORTED"


async def test_a_sensing_component_needs_no_binding(robot: Robot) -> None:
    assert await execute(robot.client, unit(EYES, "start", "c1")) == "OK"
    assert await robot.client.completed("c1") == "OK"


async def test_a_trusted_session_skips_the_binding_check(robot: Robot) -> None:
    await bound(robot, GRIP)
    parent = Peer(robot.engine, trusted=True)
    assert await execute(parent, unit(GRIP, "grip", "c1", force="1.0")) == "OK"
    assert await parent.completed("c1") == "OK"


async def test_bind_of_an_unknown_component_is_unsupported(robot: Robot) -> None:
    result = await robot.client.call("rois.command.bind", component_ref="robot/arm")
    assert result["return_code"] == "UNSUPPORTED"


# -- Execute -------------------------------------------------------------------------------


async def test_execute_refuses_what_no_component_serves(robot: Robot) -> None:
    await bound(robot, GRIP)
    assert await execute(robot.client, unit("robot/arm", "grip", "c1")) == "UNSUPPORTED"
    assert await execute(robot.client, unit(GRIP, "start", "c1")) == "UNSUPPORTED"
    # Navigation declares no "dance", and the check comes before the binding check.
    assert await execute(robot.client, unit(NAV, "dance", "c1")) == "UNSUPPORTED"


async def test_execute_refuses_arguments_that_do_not_fit(robot: Robot) -> None:
    await bound(robot, GRIP)
    assert await execute(robot.client, unit(GRIP, "grip", "c1", speed="1.0")) == "BAD_PARAMETER"
    assert await execute(robot.client, unit(GRIP, "grip", "c1", force="hard")) == "BAD_PARAMETER"


async def test_execute_refuses_an_empty_or_reused_command_id(robot: Robot) -> None:
    await bound(robot, GRIP)
    assert await execute(robot.client, {"command_list": []}) == "BAD_PARAMETER"
    assert await execute(robot.client, unit(GRIP, "grip", "", force="1.0")) == "BAD_PARAMETER"
    twice = unit(GRIP, "grip", "c1", force="1.0")
    assert await execute(robot.client, twice, twice) == "BAD_PARAMETER"
    assert await execute(robot.client, twice) == "OK"
    assert await execute(robot.client, twice) == "BAD_PARAMETER"


async def test_execute_refuses_a_command_id_in_the_namespace_of_an_engine(
    robot: Robot,
) -> None:
    await bound(robot, GRIP)
    taken = unit(GRIP, "grip", "robot/param-9", force="1.0")
    assert await execute(robot.client, taken) == "BAD_PARAMETER"
    free = unit(GRIP, "grip", "kitchen/visit-1", force="1.0")
    assert await execute(robot.client, free) == "OK"


async def test_a_command_completes_with_its_results(robot: Robot) -> None:
    await bound(robot, GRIP)
    assert await execute(robot.client, unit(GRIP, "grip", "c1", force="2.5")) == "OK"
    assert await robot.client.completed("c1") == "OK"
    assert robot.gripper.forces == [2.5]
    result = await robot.client.call(
        "rois.command.get_command_result", command_id="c1", condition=""
    )
    assert result["results"] == [{"name": "held", "data_type_ref": "bool", "value": "true"}]


async def test_get_command_result_needs_a_known_id_and_an_empty_filter(robot: Robot) -> None:
    await bound(robot, GRIP)
    await execute(robot.client, unit(GRIP, "grip", "c1", force="1.0"))
    await robot.client.completed("c1")
    unknown = await robot.client.call(
        "rois.command.get_command_result", command_id="c9", condition=""
    )
    assert unknown["return_code"] == "BAD_PARAMETER"
    filtered = await robot.client.call(
        "rois.command.get_command_result", command_id="c1", condition=eq(COMPONENT_REF, GRIP)
    )
    assert filtered["return_code"] == "BAD_PARAMETER"


async def test_command_failed_ends_the_command_with_its_status(robot: Robot) -> None:
    await bound(robot, NAV)
    await execute(robot.client, unit(NAV, "suspend", "c1"))
    assert await robot.client.completed("c1") == "OUT_OF_RESOURCES"


async def test_any_other_exception_ends_the_command_with_error(robot: Robot) -> None:
    await bound(robot, NAV)
    await execute(robot.client, unit(NAV, "resume", "c1"))
    assert await robot.client.completed("c1") == "ERROR"


async def test_a_command_past_its_timeout_ends_with_timeout(robot: Robot) -> None:
    await bound(robot, GRIP)
    await execute(robot.client, unit(GRIP, "squeeze", "c1"))
    assert await robot.client.completed("c1") == "TIMEOUT"


async def test_stop_aborts_the_running_start(robot: Robot) -> None:
    await bound(robot, NAV)
    await execute(robot.client, unit(NAV, "start", "c1"))
    await execute(robot.client, unit(NAV, "stop", "c2"))
    assert await robot.client.completed("c2") == "OK"
    assert await robot.client.completed("c1") == "ABORT"
    assert robot.navigation.stops == 1


async def test_a_new_start_aborts_the_running_one(robot: Robot) -> None:
    await bound(robot, NAV)
    await execute(robot.client, unit(NAV, "start", "c1"))
    await execute(robot.client, unit(NAV, "start", "c2"))
    assert await robot.client.completed("c1") == "ABORT"
    assert robot.navigation.stops == 1
    assert robot.client.status_of("c2") is None
    robot.navigation.arrive.set()
    assert await robot.client.completed("c2") == "OK"


async def test_concurrent_starts_leave_one_start_for_stop_to_abort(robot: Robot) -> None:
    await bound(robot, NAV)
    await execute(robot.client, unit(NAV, "start", "c1"))
    both = {"command_list": [unit(NAV, "start", "c2"), unit(NAV, "start", "c3")]}
    assert await execute(robot.client, both) == "OK"
    assert await robot.client.completed("c1") == "ABORT"
    assert await robot.client.completed("c2") == "ABORT"
    await execute(robot.client, unit(NAV, "stop", "c4"))
    assert await robot.client.completed("c3") == "ABORT"
    status = await robot.client.call(
        "rois.query.query", query_type="component_status", condition=eq(COMPONENT_REF, NAV)
    )
    assert status["results"][0]["value"] == "READY"


class SlowToStop(Navigation):
    """A Navigation whose start takes a while to unwind when it is cancelled."""

    async def start(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0.3)
            raise


async def test_a_stop_does_not_wait_for_a_start_to_unwind() -> None:
    engine = Engine("robot")
    engine.add_component("navigation", SlowToStop())
    await engine.start()
    try:
        client = Peer(engine, trusted=True)
        await execute(client, unit(NAV, "start", "c1"))
        await asyncio.sleep(0.01)
        await execute(client, unit(NAV, "start", "c2"))
        await asyncio.sleep(0.01)
        loop = asyncio.get_running_loop()
        began = loop.time()
        await execute(client, unit(NAV, "stop", "c3"))
        assert await client.completed("c3") == "OK"
        assert loop.time() - began < 0.15
        assert await client.completed("c1") == "ABORT"
        assert await client.completed("c2") == "ABORT"
    finally:
        await engine.stop()


async def test_completed_goes_once_to_the_session_that_started_the_command(
    robot: Robot,
) -> None:
    other = Peer(robot.engine)
    await bound(robot, GRIP)
    await execute(robot.client, unit(GRIP, "grip", "c1", force="1.0"))
    await robot.client.completed("c1")
    await asyncio.sleep(0.02)
    assert len(robot.client.sent("rois.command.completed")) == 1
    assert other.notifications == []


async def test_a_component_that_could_not_connect_fails_its_commands() -> None:
    engine = Engine("robot")
    engine.add_component("navigation", Navigation(fail_connect=True))
    await engine.start()
    try:
        client = Peer(engine, trusted=True)
        await execute(client, unit(NAV, "start", "c1"))
        assert await client.completed("c1") == "ERROR"
        status = await client.call(
            "rois.query.query", query_type="component_status", condition=""
        )
        assert status["results"][0]["value"] == "ERROR"
    finally:
        await engine.stop()


async def test_component_status_follows_the_component() -> None:
    engine = Engine("robot")
    navigation = Navigation()
    engine.add_component("navigation", navigation)
    client = Peer(engine, trusted=True)

    async def status() -> str:
        result = await client.call(
            "rois.query.query", query_type="component_status", condition=""
        )
        value: str = result["results"][0]["value"]
        return value

    assert await status() == "UNINITIALIZED"
    await engine.start()
    try:
        assert await status() == "READY"
        await execute(client, unit(NAV, "start", "c1"))
        await asyncio.sleep(0.02)
        assert await status() == "BUSY"
        navigation.arrive.set()
        await client.completed("c1")
        assert await status() == "READY"
    finally:
        await engine.stop()


# -- Sequences -----------------------------------------------------------------------------


async def test_the_items_of_a_sequence_run_in_order(robot: Robot) -> None:
    await bound(robot, NAV, GRIP)
    items = (unit(NAV, "start", "c1"), unit(GRIP, "grip", "c2", force="1.0"))
    assert await execute(robot.client, *items) == "OK"
    await asyncio.sleep(0.05)
    assert robot.gripper.forces == []
    robot.navigation.arrive.set()
    assert await robot.client.completed("c1") == "OK"
    assert await robot.client.completed("c2") == "OK"
    assert robot.gripper.forces == [1.0]


async def test_the_commands_of_a_concurrent_item_run_together(robot: Robot) -> None:
    await bound(robot, NAV, GRIP)
    together = {
        "command_list": [unit(NAV, "start", "c1"), unit(GRIP, "grip", "c2", force="1.0")],
    }
    assert await execute(robot.client, together) == "OK"
    assert await robot.client.completed("c2") == "OK"
    assert robot.client.status_of("c1") is None
    robot.navigation.arrive.set()
    assert await robot.client.completed("c1") == "OK"


async def test_a_failed_command_aborts_the_rest_of_the_sequence(robot: Robot) -> None:
    await bound(robot, NAV, GRIP)
    items = (
        unit(NAV, "suspend", "c1"),
        unit(GRIP, "grip", "c2", force="1.0"),
        {"command_list": [unit(GRIP, "grip", "c3", force="1.0")]},
    )
    assert await execute(robot.client, *items) == "OK"
    assert await robot.client.completed("c1") == "OUT_OF_RESOURCES"
    assert await robot.client.completed("c2") == "ABORT"
    assert await robot.client.completed("c3") == "ABORT"
    assert robot.gripper.forces == []
    never_ran = await robot.client.call(
        "rois.command.get_command_result", command_id="c2", condition=""
    )
    assert never_ran == {"return_code": "OK", "results": []}


async def test_delay_time_waits_before_its_item(robot: Robot) -> None:
    await bound(robot, GRIP)
    loop = asyncio.get_running_loop()
    began = loop.time()
    await execute(robot.client, unit(GRIP, "grip", "c1", delay_time=100, force="1.0"))
    await robot.client.completed("c1")
    assert loop.time() - began >= 0.1


async def test_each_command_of_a_concurrent_item_waits_its_own_delay(robot: Robot) -> None:
    await bound(robot, GRIP)
    loop = asyncio.get_running_loop()
    began = loop.time()
    together = {
        "command_list": [
            unit(GRIP, "grip", "c1", force="1.0"),
            unit(GRIP, "grip", "c2", delay_time=100, force="2.0"),
        ],
    }
    await execute(robot.client, together)
    await robot.client.completed("c1")
    assert robot.client.status_of("c2") is None
    await robot.client.completed("c2")
    assert loop.time() - began >= 0.1
    assert robot.gripper.forces == [1.0, 2.0]


# -- Parameters ----------------------------------------------------------------------------


async def test_parameters_start_at_the_defaults_of_the_profile(robot: Robot) -> None:
    result = await robot.client.call("rois.command.get_parameter", component_ref=NAV)
    assert result["parameters"] == [
        {"name": "time_limit", "data_type_ref": "int", "value": "0"},
        {"name": "routing_policy", "data_type_ref": "string", "value": "time"},
    ]


async def test_set_parameter_applies_and_stores_new_values(robot: Robot) -> None:
    client = await bound(robot, NAV)
    result = await client.call(
        "rois.command.set_parameter",
        component_ref=NAV,
        parameters=[{"name": "target_positions", "data_type_ref": "", "value": '["kitchen"]'}],
    )
    assert result["return_code"] == "OK"
    assert result["command_id"].startswith("robot/param-")
    assert await client.completed(result["command_id"]) == "OK"
    assert robot.navigation.applied == [{"target_positions": ["kitchen"]}]
    stored = await client.call("rois.command.get_parameter", component_ref=NAV)
    assert stored["parameters"][0] == {
        "name": "target_positions",
        "data_type_ref": "string[]",
        "value": '["kitchen"]',
    }


async def test_a_refused_value_keeps_the_old_one(robot: Robot) -> None:
    client = await bound(robot, NAV)
    robot.navigation.refuse = True
    result = await client.call(
        "rois.command.set_parameter",
        component_ref=NAV,
        parameters=[{"name": "routing_policy", "data_type_ref": "string", "value": "distance"}],
    )
    assert await client.completed(result["command_id"]) == "ERROR"
    stored = await client.call("rois.command.get_parameter", component_ref=NAV)
    assert {"name": "routing_policy", "data_type_ref": "string", "value": "time"} in stored[
        "parameters"
    ]


@pytest.mark.parametrize(
    ("ref", "name", "value", "return_code"),
    [
        ("robot/arm", "time_limit", "1", "UNSUPPORTED"),
        (NAV, "speed", "1", "BAD_PARAMETER"),
        (NAV, "time_limit", "soon", "BAD_PARAMETER"),
    ],
)
async def test_set_parameter_checks_the_component_names_and_types(
    robot: Robot, ref: str, name: str, value: str, return_code: str
) -> None:
    client = await bound(robot, NAV)
    result = await client.call(
        "rois.command.set_parameter",
        component_ref=ref,
        parameters=[{"name": name, "data_type_ref": "", "value": value}],
    )
    assert result["return_code"] == return_code


async def test_set_parameter_needs_the_binding(robot: Robot) -> None:
    result = await robot.client.call(
        "rois.command.set_parameter",
        component_ref=NAV,
        parameters=[{"name": "time_limit", "data_type_ref": "int", "value": "5"}],
    )
    assert result["return_code"] == "OUT_OF_RESOURCES"


async def test_set_parameter_runs_as_a_command_of_a_sequence(robot: Robot) -> None:
    client = await bound(robot, NAV)
    assert await execute(client, unit(NAV, "set_parameter", "c1", time_limit="30")) == "OK"
    assert await client.completed("c1") == "OK"
    assert robot.navigation.applied == [{"time_limit": 30}]
    assert await execute(client, unit(NAV, "set_parameter", "c2", speed="3")) == "BAD_PARAMETER"


# -- Queries -------------------------------------------------------------------------------


async def test_a_query_goes_to_the_one_component_that_answers_it(robot: Robot) -> None:
    width = await robot.client.call("rois.query.query", query_type="width", condition="")
    assert width["results"] == [{"name": "width", "data_type_ref": "double", "value": "0.08"}]
    several = await robot.client.call(
        "rois.query.query", query_type="component_status", condition=""
    )
    assert several["return_code"] == "BAD_PARAMETER"
    one = await robot.client.call(
        "rois.query.query", query_type="component_status", condition=eq(COMPONENT_REF, NAV)
    )
    assert one["results"] == [
        {"name": "status", "data_type_ref": "Component_Status", "value": "READY"}
    ]
    unknown = await robot.client.call("rois.query.query", query_type="mood", condition="")
    assert unknown["return_code"] == "UNSUPPORTED"


# -- Events --------------------------------------------------------------------------------


async def subscribe(peer: Peer, ref: str = NAV, event_type: str = "reached_target") -> str:
    result = await peer.call(
        "rois.event.subscribe", event_type=event_type, condition=eq(COMPONENT_REF, ref)
    )
    assert result["return_code"] == "OK", result
    subscribe_id: str = result["subscribe_id"]
    return subscribe_id


async def test_an_event_reaches_the_session_that_subscribed(robot: Robot) -> None:
    client = await bound(robot, NAV)
    other = Peer(robot.engine)
    subscribe_id = await subscribe(client)
    assert subscribe_id.startswith("robot/sub-")
    assert robot.navigation.subscribed == 1
    await execute(client, unit(NAV, "start", "c1"))
    robot.navigation.arrive.set()
    await client.completed("c1")
    [event] = client.sent("rois.event.notify_event")
    assert event["subscribe_id"] == subscribe_id
    assert event["event_type"] == "reached_target"
    assert event["event_id"].startswith("robot/evt-")
    assert event["results"] == [
        {"name": "target", "data_type_ref": "string", "value": "home"},
        {"name": "is_final_target", "data_type_ref": "bool", "value": "true"},
    ]
    assert other.notifications == []
    detail = await client.call(
        "rois.event.get_event_detail", event_id=event["event_id"], condition=""
    )
    assert detail["results"] == event["results"]


async def test_subscribe_selects_one_component_that_serves_the_event(robot: Robot) -> None:
    unknown = await robot.client.call(
        "rois.event.subscribe", event_type="person_left", condition=""
    )
    assert unknown["return_code"] == "UNSUPPORTED"
    one = await robot.client.call(
        "rois.event.subscribe", event_type="person_detected", condition=""
    )
    assert one["return_code"] == "OK"


async def test_unsubscribe_ends_the_events(robot: Robot) -> None:
    client = await bound(robot, NAV)
    subscribe_id = await subscribe(client)
    other = Peer(robot.engine)
    # Another session cannot end a subscription it does not hold.
    await other.call("rois.event.unsubscribe", subscribe_id=subscribe_id)
    await execute(client, unit(NAV, "start", "c1"))
    robot.navigation.arrive.set()
    await client.completed("c1")
    assert len(client.sent("rois.event.notify_event")) == 1
    result = await client.call("rois.event.unsubscribe", subscribe_id=subscribe_id)
    assert result["return_code"] == "OK"
    await execute(client, unit(NAV, "start", "c2"))
    await client.completed("c2")
    assert len(client.sent("rois.event.notify_event")) == 1


async def test_an_event_expires_after_its_lifetime() -> None:
    engine = Engine("robot", event_lifetime=0.05)
    navigation = Navigation()
    navigation.arrive.set()
    engine.add_component("navigation", navigation)
    await engine.start()
    try:
        client = Peer(engine, trusted=True)
        await subscribe(client)
        await execute(client, unit(NAV, "start", "c1"))
        await client.completed("c1")
        [event] = client.sent("rois.event.notify_event")
        assert event["expire"]
        await asyncio.sleep(0.1)
        detail = await client.call(
            "rois.event.get_event_detail", event_id=event["event_id"], condition=""
        )
        assert detail["return_code"] == "BAD_PARAMETER"
    finally:
        await engine.stop()


async def test_events_emitted_from_another_thread_arrive(robot: Robot) -> None:
    await subscribe(robot.client)
    thread = threading.Thread(
        target=robot.navigation.emit,
        args=("reached_target",),
        kwargs={"target": "dock", "is_final_target": False},
    )
    thread.start()
    thread.join()
    await wait_until(lambda: len(robot.client.sent("rois.event.notify_event")) == 1)
    [event] = robot.client.sent("rois.event.notify_event")
    assert event["results"][0]["value"] == "dock"


async def test_closing_a_session_releases_its_bindings_and_subscriptions(robot: Robot) -> None:
    client = await bound(robot, NAV)
    await subscribe(client)
    local = robot.engine._local
    assert local._subscriptions
    await client.close()
    assert not local._subscriptions
    other = Peer(robot.engine)
    assert (await other.call("rois.command.bind", component_ref=NAV))["return_code"] == "OK"


async def test_disconnect_releases_the_bindings_of_the_session(robot: Robot) -> None:
    client = await bound(robot, NAV)
    assert (await client.call("rois.system.disconnect"))["return_code"] == "OK"
    other = Peer(robot.engine)
    assert (await other.call("rois.command.bind", component_ref=NAV))["return_code"] == "OK"
