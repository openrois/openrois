"""The Gateway class: start, stop, and serving clients and child engines."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from openrois.engine import Engine, WsClient
from websockets.asyncio.client import ClientConnection, connect

from openrois.gateway import Gateway, GatewayConfig


async def wait_until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    """Poll a condition until it holds, failing the test after ``timeout`` seconds."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        if loop.time() > deadline:
            raise AssertionError("Condition not met in time.")
        await asyncio.sleep(0.01)


async def call(connection: ClientConnection, method: str) -> dict[str, Any]:
    """Send one request and return its result, skipping notifications."""
    await connection.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method}))
    while True:
        message: dict[str, Any] = json.loads(await connection.recv())
        if message.get("id") == 1:
            result: dict[str, Any] = message["result"]
            return result


@pytest.fixture
async def gateway() -> AsyncIterator[Gateway]:
    running = Gateway(GatewayConfig(port=0, engine_id="lab", child_timeout=0.5))
    await running.start()
    try:
        yield running
    finally:
        await running.stop()


async def test_a_client_reads_the_profile_of_the_configured_engine(gateway: Gateway) -> None:
    async with connect(f"ws://127.0.0.1:{gateway.port}") as client:
        profile = (await call(client, "rois.system.get_profile"))["profile"]
    assert profile["identifier"]["code"] == "lab"


async def test_an_adapter_registers_with_the_gateway(gateway: Gateway) -> None:
    adapter = asyncio.create_task(
        WsClient(Engine("robot"), f"ws://127.0.0.1:{gateway.port}").run_async()
    )
    try:
        await wait_until(lambda: gateway.engine.child_engine_ids() == ["robot"])
        async with connect(f"ws://127.0.0.1:{gateway.port}") as client:
            profile = (await call(client, "rois.system.get_profile"))["profile"]
        assert [p["identifier"]["code"] for p in profile["sub_profiles"]] == ["robot"]
    finally:
        adapter.cancel()
        await asyncio.gather(adapter, return_exceptions=True)


async def test_run_serves_until_the_stop_event_is_set() -> None:
    gateway = Gateway(GatewayConfig(port=0))
    stop = asyncio.Event()
    task = asyncio.create_task(gateway.run(stop))

    def listening() -> bool:
        try:
            return gateway.port > 0
        except RuntimeError:
            return False

    await wait_until(listening)
    async with connect(f"ws://127.0.0.1:{gateway.port}") as client:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
        await asyncio.wait_for(client.wait_closed(), timeout=2.0)
        assert client.close_code == 1001
