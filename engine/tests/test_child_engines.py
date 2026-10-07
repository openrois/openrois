"""Child engines on real sockets: discovery, refusal, routing and a gateway under a gateway."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from openrois.interfaces.condition import COMPONENT_REF, eq

from openrois.engine import Engine, WsClient, WsServer
from tests._support import (
    CHILD_TIMEOUT,
    Adapter,
    FakeChild,
    Gateway,
    Gripper,
    Navigation,
    PersonDetection,
    RpcClient,
    start_adapter,
    unit,
    wait_until,
)

NAV = "robot/navigation"


# -- Discovery -----------------------------------------------------------------------------


async def test_the_adapter_path_is_asked_for_its_profile(gateway: Gateway) -> None:
    child = await FakeChild.connect(gateway)
    request = await child.request()
    assert request["method"] == "rois.system.get_profile"
    assert request["params"] == {"condition": ""}


async def test_an_adapter_is_added_with_its_components(
    adapter: Adapter, client: RpcClient
) -> None:
    result = await client.call("rois.system.get_profile", condition="")
    profile = result["profile"]
    assert profile["identifier"]["code"] == "gateway"
    assert profile["component_ids"] == [NAV]
    [robot] = profile["sub_profiles"]
    assert robot["identifier"]["code"] == "robot"
    assert robot["component_ids"] == [NAV]
    assert result["component_profiles"][NAV]["name"] == "navigation"


async def test_a_condition_trims_the_sub_profiles(gateway: Gateway, client: RpcClient) -> None:
    first = await start_adapter(gateway.url, gateway, "robot_a")
    second = await start_adapter(gateway.url, gateway, "robot_b", {"eyes": PersonDetection()})
    try:
        everything = await client.call("rois.system.get_profile", condition="")
        codes = [p["identifier"]["code"] for p in everything["profile"]["sub_profiles"]]
        assert codes == ["robot_a", "robot_b"]
        eyes = await client.call(
            "rois.system.get_profile", condition=eq(COMPONENT_REF, "robot_b/eyes")
        )
        [only] = eyes["profile"]["sub_profiles"]
        assert only["identifier"]["code"] == "robot_b"
        assert eyes["profile"]["component_ids"] == ["robot_b/eyes"]
    finally:
        await first.stop()
        await second.stop()


async def test_clients_hear_when_an_adapter_comes_and_goes(
    gateway: Gateway, client: RpcClient
) -> None:
    adapter = await start_adapter(gateway.url, gateway)
    await client.notification("rois.system.profile_changed")
    await adapter.stop()
    await wait_until(lambda: len(client.sent("rois.system.profile_changed")) == 2)
    assert gateway.engine.child_engine_ids() == []


async def test_a_changed_child_profile_is_read_again(gateway: Gateway, client: RpcClient) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("cam")
    await wait_until(lambda: gateway.engine.child_engine_ids() == ["cam"])
    await child.connection.send(
        json.dumps({"jsonrpc": "2.0", "method": "rois.system.profile_changed", "params": {}})
    )
    await child.answer_profile("cam", refs=["cam/camera", "cam/camera_2"])
    await wait_until(lambda: len(client.sent("rois.system.profile_changed")) == 2)
    found = await client.call("rois.command.search", condition="")
    assert found["component_ref_list"] == ["cam/camera", "cam/camera_2"]


async def test_a_changed_profile_that_reuses_an_engine_id_closes_the_child(
    gateway: Gateway, adapter: Adapter, client: RpcClient
) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("floor")
    await wait_until(lambda: gateway.engine.child_engine_ids() == ["robot", "floor"])
    await child.connection.send(
        json.dumps({"jsonrpc": "2.0", "method": "rois.system.profile_changed", "params": {}})
    )
    await child.answer_profile(
        "floor", refs=["floor/camera", "robot/camera"], sub_engine_ids=("robot",)
    )
    code, reason = await child.closed()
    assert (code, reason) == (1008, "Engine id robot is already in use.")
    await wait_until(lambda: gateway.engine.child_engine_ids() == ["robot"])
    found = await client.call("rois.command.search", condition="")
    assert found["component_ref_list"] == [NAV]


# -- Refusal -------------------------------------------------------------------------------


async def test_a_child_that_never_answers_discovery_is_refused(gateway: Gateway) -> None:
    child = await FakeChild.connect(gateway)
    code, reason = await child.closed()
    assert code == 1008
    assert reason == "Discovery failed with TIMEOUT."


@pytest.mark.parametrize("engine_id", ["", "lab/robot"])
async def test_an_invalid_engine_id_is_refused(gateway: Gateway, engine_id: str) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile(engine_id, refs=[])
    code, reason = await child.closed()
    assert code == 1008
    assert reason is not None and reason.startswith("Invalid engine id")


async def test_a_ref_another_engine_owns_is_refused(gateway: Gateway) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("cam", refs=["robot/camera"])
    code, reason = await child.closed()
    assert code == 1008
    assert reason == "Component ref 'robot/camera' does not start with an engine id of the child."


async def test_an_engine_id_twice_in_one_child_is_refused(gateway: Gateway) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("floor", refs=[], sub_engine_ids=("cam", "cam"))
    code, reason = await child.closed()
    assert (code, reason) == (1008, "Engine id cam appears twice in the child.")


async def test_a_duplicate_engine_id_leaves_the_first_child_in_place(
    gateway: Gateway, adapter: Adapter
) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("robot")
    code, reason = await child.closed()
    assert (code, reason) == (1008, "Engine id robot is already in use.")
    assert gateway.engine.child_engine_ids() == ["robot"]


async def test_the_id_of_the_gateway_itself_is_taken(gateway: Gateway) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("gateway")
    code, reason = await child.closed()
    assert (code, reason) == (1008, "Engine id gateway is already in use.")


async def test_a_refused_adapter_waits_before_it_reconnects(
    gateway: Gateway, adapter: Adapter, caplog: pytest.LogCaptureFixture
) -> None:
    duplicate = Engine("robot")
    duplicate.add_component("navigation", Navigation())
    task = asyncio.create_task(WsClient(duplicate, gateway.url).run_async())
    try:
        with caplog.at_level(logging.WARNING, logger="openrois.engine.ws_server"):
            await asyncio.sleep(0.8)
        refusals = [r for r in caplog.records if "already in use" in r.getMessage()]
        assert len(refusals) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


# -- Routing -------------------------------------------------------------------------------


async def test_a_sequence_runs_across_two_adapters(gateway: Gateway, client: RpcClient) -> None:
    navigation = Navigation()
    first = await start_adapter(gateway.url, gateway, "robot_a", {"navigation": navigation})
    second = await start_adapter(gateway.url, gateway, "robot_b", {"gripper": Gripper()})
    try:
        for ref in ("robot_a/navigation", "robot_b/gripper"):
            assert (await client.call("rois.command.bind", component_ref=ref))[
                "return_code"
            ] == "OK"
        items = [
            unit("robot_a/navigation", "start", "c1"),
            unit("robot_b/gripper", "grip", "c2", force="1.5"),
        ]
        result = await client.call("rois.command.execute", command_unit_list=items)
        assert result["return_code"] == "OK"
        await asyncio.sleep(0.05)
        assert client.sent("rois.command.completed") == []
        navigation.arrive.set()
        assert await client.completed("c1") == "OK"
        assert await client.completed("c2") == "OK"
        held = await client.call(
            "rois.command.get_command_result", command_id="c2", condition=""
        )
        assert held["results"] == [{"name": "held", "data_type_ref": "bool", "value": "true"}]
    finally:
        await first.stop()
        await second.stop()


async def test_the_ids_of_a_child_name_the_engine_that_owns_them(
    adapter: Adapter, client: RpcClient
) -> None:
    await client.call("rois.command.bind", component_ref=NAV)
    subscribed = await client.call(
        "rois.event.subscribe", event_type="reached_target", condition=eq(COMPONENT_REF, NAV)
    )
    assert subscribed["subscribe_id"].startswith("robot/sub-")
    configured = await client.call(
        "rois.command.set_parameter",
        component_ref=NAV,
        parameters=[{"name": "target_positions", "data_type_ref": "", "value": '["dock"]'}],
    )
    assert configured["command_id"].startswith("robot/param-")
    assert await client.completed(configured["command_id"]) == "OK"

    await client.call("rois.command.execute", command_unit_list=[unit(NAV, "start", "c1")])
    navigation = adapter.components["navigation"]
    assert isinstance(navigation, Navigation)
    navigation.arrive.set()
    event = await client.notification("rois.event.notify_event")
    assert event["subscribe_id"] == subscribed["subscribe_id"]
    assert event["event_id"].startswith("robot/evt-")
    assert event["results"][0]["value"] == "dock"
    detail = await client.call(
        "rois.event.get_event_detail", event_id=event["event_id"], condition=""
    )
    assert detail["results"] == event["results"]


async def test_a_delay_is_waited_once_however_deep_the_component(
    adapter: Adapter, client: RpcClient
) -> None:
    await client.call("rois.command.bind", component_ref=NAV)
    await client.call(
        "rois.command.execute", command_unit_list=[unit(NAV, "stop", "c1", delay_time=300)]
    )
    loop = asyncio.get_running_loop()
    began = loop.time()
    assert await client.completed("c1") == "OK"
    assert 0.25 <= loop.time() - began < 0.5


async def test_a_set_parameter_id_assigned_again_after_a_restart_completes(
    gateway: Gateway, client: RpcClient
) -> None:
    async def configure() -> str:
        result = await client.call(
            "rois.command.set_parameter",
            component_ref=NAV,
            parameters=[{"name": "time_limit", "data_type_ref": "int", "value": "5"}],
        )
        command_id: str = result["command_id"]
        return command_id

    first = await start_adapter(gateway.url, gateway)
    await client.call("rois.command.bind", component_ref=NAV)
    before = await configure()
    await client.completed(before)
    await first.stop()
    await wait_until(lambda: gateway.engine.child_engine_ids() == [])
    second = await start_adapter(gateway.url, gateway)
    try:
        await client.call("rois.command.bind", component_ref=NAV)
        after = await configure()
        assert after == before
        await wait_until(
            lambda: [p["command_id"] for p in client.sent("rois.command.completed")]
            == [before, after]
        )
        result = await client.call(
            "rois.command.get_command_result", command_id=after, condition=""
        )
        assert result["return_code"] == "OK"
    finally:
        await second.stop()


async def test_the_reply_to_subscribe_comes_before_the_first_event(
    gateway: Gateway, client: RpcClient
) -> None:
    eyes = {"eyes": PersonDetection(ticking=True)}
    ticking = await start_adapter(gateway.url, gateway, "robot", eyes)
    try:
        subscribe_ids = []
        for _ in range(10):
            subscribed = await client.call(
                "rois.event.subscribe",
                event_type="person_detected",
                condition=eq(COMPONENT_REF, "robot/eyes"),
            )
            subscribe_ids.append(subscribed["subscribe_id"])
        await asyncio.sleep(0.05)
        for subscribe_id in subscribe_ids:
            reply_at = next(
                i
                for i, m in enumerate(client.messages)
                if m.get("result", {}).get("subscribe_id") == subscribe_id
            )
            first_event_at = next(
                i
                for i, m in enumerate(client.messages)
                if m.get("method") == "rois.event.notify_event"
                and m["params"]["subscribe_id"] == subscribe_id
            )
            assert reply_at < first_event_at
    finally:
        await ticking.stop()


async def test_an_id_outside_the_child_counts_as_error(
    gateway: Gateway, client: RpcClient
) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("cam")
    await wait_until(lambda: gateway.engine.child_engine_ids() == ["cam"])
    pending = client.send(
        "rois.event.subscribe",
        {"event_type": "person_detected", "condition": eq(COMPONENT_REF, "cam/camera")},
    )
    request = await child.request()
    assert request["method"] == "rois.event.subscribe"
    await child.reply(request, {"return_code": "OK", "subscribe_id": "robot/sub-1"})
    reply = await asyncio.wait_for(pending, timeout=2.0)
    assert reply["result"]["return_code"] == "ERROR"


async def test_an_id_the_child_already_gave_out_counts_as_error(
    gateway: Gateway, client: RpcClient
) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("cam")
    await wait_until(lambda: gateway.engine.child_engine_ids() == ["cam"])
    params = {"event_type": "person_detected", "condition": eq(COMPONENT_REF, "cam/camera")}
    replies = []
    for _ in range(2):
        pending = client.send("rois.event.subscribe", params)
        await child.reply(
            await child.request(), {"return_code": "OK", "subscribe_id": "cam/sub-1"}
        )
        replies.append(await asyncio.wait_for(pending, timeout=2.0))
    assert [r["result"]["return_code"] for r in replies] == ["OK", "ERROR"]


async def test_a_command_id_taken_by_a_running_command_keeps_both_completions(
    gateway: Gateway, adapter: Adapter, client: RpcClient
) -> None:
    await client.call("rois.command.bind", component_ref=NAV)
    # The client names a command in the namespace of an engine that is not there yet.
    started = await client.call(
        "rois.command.execute", command_unit_list=[unit(NAV, "start", "cam/param-1")]
    )
    assert started["return_code"] == "OK"
    child = await FakeChild.connect(gateway)
    await child.answer_profile("cam")
    await wait_until(lambda: gateway.engine.child_engine_ids() == ["robot", "cam"])
    pending = client.send(
        "rois.command.set_parameter", {"component_ref": "cam/camera", "parameters": []}
    )
    await child.reply(await child.request(), {"return_code": "OK", "command_id": "cam/param-1"})
    assert (await asyncio.wait_for(pending, timeout=2.0))["result"]["return_code"] == "OK"
    completed = {"command_id": "cam/param-1", "status": "OK"}
    await child.connection.send(
        json.dumps({"jsonrpc": "2.0", "method": "rois.command.completed", "params": completed})
    )
    await wait_until(lambda: len(client.sent("rois.command.completed")) == 1)
    navigation = adapter.components["navigation"]
    assert isinstance(navigation, Navigation)
    navigation.arrive.set()
    await wait_until(lambda: len(client.sent("rois.command.completed")) == 2)
    assert client.sent("rois.command.completed") == [completed, completed]


async def test_a_subscription_whose_reply_comes_too_late_is_ended(
    gateway: Gateway, client: RpcClient
) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("cam")
    await wait_until(lambda: gateway.engine.child_engine_ids() == ["cam"])
    pending = client.send(
        "rois.event.subscribe",
        {"event_type": "person_detected", "condition": eq(COMPONENT_REF, "cam/camera")},
    )
    request = await child.request()
    reply = await asyncio.wait_for(pending, timeout=2.0)
    assert reply["result"]["return_code"] == "TIMEOUT"
    await child.reply(request, {"return_code": "OK", "subscribe_id": "cam/sub-1"})
    ended = await child.request()
    assert ended["method"] == "rois.event.unsubscribe"
    assert ended["params"] == {"subscribe_id": "cam/sub-1"}


async def test_a_child_that_sends_garbage_stays_connected(
    gateway: Gateway, client: RpcClient
) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("cam")
    await wait_until(lambda: gateway.engine.child_engine_ids() == ["cam"])
    await child.connection.send("[" * 100_000)
    await child.connection.send(json.dumps({"jsonrpc": "2.0", "id": 99, "result": "stray"}))
    pending = client.send(
        "rois.query.query",
        {"query_type": "component_status", "condition": eq(COMPONENT_REF, "cam/camera")},
    )
    request = await child.request()
    status = {"name": "status", "data_type_ref": "Component_Status", "value": "READY"}
    await child.reply(request, {"return_code": "OK", "results": [status]})
    reply = await asyncio.wait_for(pending, timeout=2.0)
    assert reply["result"]["results"] == [status]


async def test_a_reply_reaches_the_client_before_the_completion_it_causes(
    adapter: Adapter, client: RpcClient
) -> None:
    await client.call("rois.command.bind", component_ref=NAV)
    command_ids = []
    for _ in range(20):
        configured = await client.call(
            "rois.command.set_parameter",
            component_ref=NAV,
            parameters=[{"name": "time_limit", "data_type_ref": "int", "value": "5"}],
        )
        command_ids.append(configured["command_id"])
        await client.completed(configured["command_id"])

    def position(command_id: str, kind: str) -> int:
        for index, message in enumerate(client.messages):
            if kind == "reply" and message.get("result", {}).get("command_id") == command_id:
                return index
            if (
                kind == "completed"
                and message.get("method") == "rois.command.completed"
                and message["params"]["command_id"] == command_id
            ):
                return index
        raise AssertionError(f"No {kind} for {command_id}")

    for command_id in command_ids:
        assert position(command_id, "reply") < position(command_id, "completed")


async def test_a_child_that_disconnects_fails_its_running_commands(
    adapter: Adapter, client: RpcClient
) -> None:
    await client.call("rois.command.bind", component_ref=NAV)
    await client.call("rois.command.execute", command_unit_list=[unit(NAV, "start", "c1")])
    await asyncio.sleep(0.05)
    await adapter.stop()
    assert await client.completed("c1") == "ERROR"


async def test_a_child_that_stops_replying_times_out(gateway: Gateway, client: RpcClient) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("cam")
    await wait_until(lambda: gateway.engine.child_engine_ids() == ["cam"])
    loop = asyncio.get_running_loop()
    began = loop.time()
    status = await client.call(
        "rois.query.query", query_type="component_status", condition=eq(COMPONENT_REF, "cam/camera")
    )
    assert status["return_code"] == "TIMEOUT"
    assert loop.time() - began >= CHILD_TIMEOUT
    await client.call("rois.command.execute", command_unit_list=[unit("cam/camera", "start", "c1")])
    assert await client.completed("c1") == "TIMEOUT"


async def test_stopping_the_server_removes_every_child(gateway: Gateway, adapter: Adapter) -> None:
    await gateway.server.stop()
    assert gateway.engine.child_engine_ids() == []


# -- A gateway under a gateway ---------------------------------------------------------------


async def test_a_gateway_serves_the_engines_below_another_gateway(
    gateway: Gateway, client: RpcClient
) -> None:
    # A middle tier with a component of its own, a child adapter, and the top gateway as
    # its parent. Its WsClient starts and stops the engine.
    middle = Engine("floor")
    middle.add_component("eyes", PersonDetection())
    middle_server = WsServer(middle, child_timeout=CHILD_TIMEOUT)
    await middle_server.start("127.0.0.1", 0)
    up = asyncio.create_task(WsClient(middle, gateway.url).run_async())
    navigation = Navigation()
    robot = await start_adapter(
        f"ws://127.0.0.1:{middle_server.port}", None, "robot", {"navigation": navigation}
    )
    try:

        async def refs() -> list[str]:
            found = await client.call("rois.command.search", condition="")
            listed: list[str] = found["component_ref_list"]
            return listed

        loop = asyncio.get_running_loop()
        deadline = loop.time() + 3.0
        while await refs() != ["floor/eyes", NAV]:
            assert loop.time() < deadline, await refs()
            await asyncio.sleep(0.02)

        profile = (await client.call("rois.system.get_profile", condition=""))["profile"]
        [floor] = profile["sub_profiles"]
        assert floor["identifier"]["code"] == "floor"
        assert [p["identifier"]["code"] for p in floor["sub_profiles"]] == ["robot"]

        await client.call("rois.command.bind", component_ref=NAV)
        subscribed = await client.call(
            "rois.event.subscribe", event_type="reached_target", condition=eq(COMPONENT_REF, NAV)
        )
        assert subscribed["subscribe_id"].startswith("robot/sub-")
        await client.call("rois.command.execute", command_unit_list=[unit(NAV, "start", "c1")])
        navigation.arrive.set()
        assert await client.completed("c1") == "OK"
        event = await client.notification("rois.event.notify_event")
        assert event["subscribe_id"] == subscribed["subscribe_id"]

        # The binding lives at the top: another client of the top gateway cannot command
        # the navigation, while the middle tier trusts its parent.
        other = await RpcClient.connect(gateway.url)
        try:
            refused = await other.call(
                "rois.command.execute", command_unit_list=[unit(NAV, "start", "c2")]
            )
            assert refused["return_code"] == "OUT_OF_RESOURCES"
        finally:
            await other.close()
    finally:
        await robot.stop()
        up.cancel()
        await asyncio.gather(up, return_exceptions=True)
        await middle_server.stop()
