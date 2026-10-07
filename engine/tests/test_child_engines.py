"""Child engines: routing by path, discovery, engine ids and disconnects."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from websockets.asyncio.client import connect

from openrois.engine import Engine, WsClient
from tests._support import (
    FakeChild,
    Gateway,
    RpcClient,
    start_adapter,
    wait_until,
)


async def test_the_adapter_path_is_asked_for_its_components(gateway: Gateway) -> None:
    async with connect(f"{gateway.url}/adapter") as child:
        request = json.loads(await child.recv())
    assert request["method"] == "rois.command.search"


async def test_any_other_path_is_a_client(gateway: Gateway) -> None:
    for path in ("", "/", "/adapters", "/client"):
        rpc = await RpcClient.connect(f"{gateway.url}{path}")
        result = await rpc.call("rois.system.connect")
        assert result["return_code"] == "OK"
        await rpc.close()


async def test_an_adapter_registers_with_its_components(
    gateway: Gateway, client: RpcClient
) -> None:
    adapter = await start_adapter(gateway, "robot")
    try:
        profile = (await client.call("rois.system.get_profile"))["profile"]
        assert profile["sub_engine_ids"] == ["robot"]
        assert "robot/Navigation" in profile["component_ids"]
    finally:
        await adapter.stop()


async def test_clients_hear_when_an_adapter_comes_and_goes(
    gateway: Gateway, client: RpcClient
) -> None:
    adapter = await start_adapter(gateway, "robot")
    assert await client.notification("rois.system.profile_changed") == {}

    await adapter.stop()
    assert await client.notification("rois.system.profile_changed") == {}
    await wait_until(lambda: gateway.child_ids() == [])


async def test_a_child_that_never_answers_discovery_is_refused(gateway: Gateway) -> None:
    child = await FakeChild.connect(gateway)
    code, reason = await child.closed()
    assert code == 1008
    assert reason == "Discovery failed with TIMEOUT."
    assert gateway.child_ids() == []


async def test_an_empty_engine_id_is_refused(gateway: Gateway) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_search("")
    assert await child.closed() == (1008, "The engine id is empty.")
    assert gateway.child_ids() == []


async def test_an_engine_id_with_a_slash_is_refused(gateway: Gateway) -> None:
    child = await FakeChild.connect(gateway)
    await child.answer_search("a/b")
    assert await child.closed() == (1008, "The engine id 'a/b' contains a slash.")


async def test_a_duplicate_engine_id_leaves_the_first_engine_registered(
    gateway: Gateway, client: RpcClient
) -> None:
    adapter = await start_adapter(gateway, "robot")
    try:
        child = await FakeChild.connect(gateway)
        await child.answer_search("robot")
        assert await child.closed() == (1008, "The engine id 'robot' is already connected.")

        assert gateway.child_ids() == ["robot"]
        result = await client.call(
            "rois.query.query",
            {"component_ref": "robot/Navigation", "query_type": "component_status"},
        )
        assert result["return_code"] == "OK"
    finally:
        await adapter.stop()


async def test_a_refused_adapter_waits_before_it_reconnects(
    gateway: Gateway, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = await start_adapter(gateway, "robot")
    duplicate = asyncio.create_task(WsClient(Engine(engine_id="robot"), gateway.url).run_async())
    try:
        with caplog.at_level(logging.WARNING, logger="openrois.engine.ws_server"):
            await asyncio.sleep(0.8)
        refusals = [r for r in caplog.records if "already connected" in r.getMessage()]
        assert len(refusals) == 1
    finally:
        duplicate.cancel()
        await asyncio.gather(duplicate, return_exceptions=True)
        await adapter.stop()


async def test_two_adapters_register_side_by_side(gateway: Gateway, client: RpcClient) -> None:
    first = await start_adapter(gateway, "robot_a")
    second = await start_adapter(gateway, "robot_b")
    try:
        profile = (await client.call("rois.system.get_profile"))["profile"]
        assert sorted(profile["sub_engine_ids"]) == ["robot_a", "robot_b"]
    finally:
        await first.stop()
        await second.stop()


async def test_stopping_the_server_unregisters_every_child(gateway: Gateway) -> None:
    adapter = await start_adapter(gateway, "robot")
    try:
        await gateway.server.stop()
        assert gateway.child_ids() == []
    finally:
        await adapter.stop()
