"""Clients on real sockets: sessions, concurrency, events and disconnects."""

from __future__ import annotations

import asyncio
import json

import pytest
from openrois.interfaces.condition import COMPONENT_REF, eq
from websockets.asyncio.client import connect

from openrois.engine import Engine, WsServer
from tests._support import (
    Adapter,
    FakeChild,
    Gateway,
    Navigation,
    RpcClient,
    unit,
    wait_until,
)

NAV = "robot/navigation"


def navigation_of(adapter: Adapter) -> Navigation:
    navigation = adapter.components["navigation"]
    assert isinstance(navigation, Navigation)
    return navigation


async def test_any_path_but_the_adapter_path_is_a_client(gateway: Gateway) -> None:
    rpc = await RpcClient.connect(f"{gateway.url}/apps/reception")
    try:
        assert (await rpc.call("rois.system.connect"))["return_code"] == "OK"
    finally:
        await rpc.close()


async def test_a_protocol_fault_is_answered_on_the_socket(gateway: Gateway) -> None:
    async with connect(gateway.url) as connection:
        await connection.send("{not json")
        reply = json.loads(await asyncio.wait_for(connection.recv(), timeout=2.0))
    assert reply["id"] is None
    assert reply["error"]["code"] == -32700


async def test_a_slow_request_leaves_the_others_unblocked(
    gateway: Gateway, client: RpcClient
) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_profile("cam")
    await wait_until(lambda: gateway.engine.child_engine_ids() == ["cam"])
    slow = client.send(
        "rois.query.query",
        {"query_type": "component_status", "condition": eq(COMPONENT_REF, "cam/camera")},
    )
    found = await client.call("rois.command.search", condition="")
    assert found["component_ref_list"] == ["cam/camera"]
    assert not slow.done()
    reply = await asyncio.wait_for(slow, timeout=2.0)
    assert reply["result"]["return_code"] == "TIMEOUT"


async def test_events_go_only_to_the_client_that_subscribed(
    gateway: Gateway, adapter: Adapter, client: RpcClient
) -> None:
    other = await RpcClient.connect(gateway.url)
    try:
        await client.call(
            "rois.event.subscribe", event_type="reached_target", condition=eq(COMPONENT_REF, NAV)
        )
        navigation_of(adapter).emit("reached_target", target="kitchen", is_final_target=True)
        event = await client.notification("rois.event.notify_event")
        assert event["results"][0]["value"] == "kitchen"
        await asyncio.sleep(0.05)
        assert other.sent("rois.event.notify_event") == []
    finally:
        await other.close()


async def test_a_disconnected_client_releases_its_bindings_and_subscriptions(
    gateway: Gateway, adapter: Adapter
) -> None:
    rpc = await RpcClient.connect(gateway.url)
    await rpc.call("rois.command.bind", component_ref=NAV)
    await rpc.call(
        "rois.event.subscribe", event_type="reached_target", condition=eq(COMPONENT_REF, NAV)
    )
    local = adapter.engine._local
    assert local._subscriptions
    await rpc.close()
    await wait_until(lambda: not local._subscriptions)
    other = await RpcClient.connect(gateway.url)
    try:
        bound = await other.call("rois.command.bind", component_ref=NAV)
        assert bound["return_code"] == "OK"
    finally:
        await other.close()


async def test_a_command_of_a_client_that_left_runs_to_its_end(
    gateway: Gateway, adapter: Adapter, client: RpcClient
) -> None:
    rpc = await RpcClient.connect(gateway.url)
    await rpc.call("rois.command.bind", component_ref=NAV)
    await rpc.call("rois.command.execute", command_unit_list=[unit(NAV, "start", "c1")])
    await rpc.close()

    async def status() -> str:
        result = await client.call(
            "rois.query.query", query_type="component_status", condition=eq(COMPONENT_REF, NAV)
        )
        value: str = result["results"][0]["value"]
        return value

    assert await status() == "BUSY"
    running = await client.call("rois.command.get_command_result", command_id="c1", condition="")
    assert running == {"return_code": "OK", "results": []}
    navigation_of(adapter).arrive.set()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 2.0
    while await status() != "READY":
        assert loop.time() < deadline
        await asyncio.sleep(0.01)


async def test_stopping_the_server_closes_clients_with_going_away(gateway: Gateway) -> None:
    async with connect(gateway.url) as connection:
        await gateway.server.stop()
        await asyncio.wait_for(connection.wait_closed(), timeout=2.0)
        assert connection.close_code == 1001


def test_the_port_is_unknown_before_the_server_starts() -> None:
    with pytest.raises(RuntimeError):
        _ = WsServer(Engine("gateway")).port
