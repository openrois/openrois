"""Gateway and adapter over a real WebSocket, in one process.

A WsServer hosts a gateway engine on an ephemeral port. A WsClient connects an
adapter engine with local components to it. A plain WebSocket client then
plays the service application and exercises discovery, queries, reservations,
commands, and events end to end.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import websockets

from openrois_core import Engine, WsClient, WsServer

from .conftest import FakeNavigation, build_engine

NAV = "robot_1/Navigation"
PARAMS = [{"name": "target_positions", "data_type_ref": "string[]", "value": '["kitchen"]'}]


class Application:
    """A minimal JSON-RPC client that plays the service application."""

    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self._next = 0
        self.notifications: list[dict[str, Any]] = []

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        self._next += 1
        await self._ws.send(json.dumps(
            {"jsonrpc": "2.0", "id": self._next, "method": method, "params": params},
        ))
        while True:
            msg = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=5))
            if msg.get("id") == self._next:
                result: dict[str, Any] = msg["result"]
                return result
            self.notifications.append(msg)

    async def code(self, method: str, **params: Any) -> str:
        return str((await self.call(method, **params))["return_code"])

    async def next_notification(self, method: str) -> dict[str, Any]:
        for msg in self.notifications:
            if msg.get("method") == method:
                self.notifications.remove(msg)
                return msg
        while True:
            msg = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=5))
            if msg.get("method") == method:
                return dict(msg)
            self.notifications.append(msg)


@pytest.fixture
async def stack() -> AsyncIterator[tuple[Application, FakeNavigation, Engine]]:
    """Gateway + connected adapter + application socket."""
    gateway = Engine(engine_id="gateway", enforce_bindings=True)
    server = WsServer(gateway)
    await server.start("127.0.0.1", 0)
    port = server._server.sockets[0].getsockname()[1]

    adapter_engine, nav = build_engine(engine_id="robot_1")
    client = WsClient(adapter_engine, f"ws://127.0.0.1:{port}")
    adapter_task = asyncio.create_task(client._run_async())

    # Wait for the gateway to have discovered the adapter.
    for _ in range(100):
        if gateway.get_sub_engines():
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("adapter never registered")

    async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
        yield Application(ws), nav, gateway

    adapter_task.cancel()
    try:
        await adapter_task
    except asyncio.CancelledError:
        pass
    await server.stop()


async def test_discovery_prefixes_adapter_components(stack) -> None:
    app, _, _ = stack
    assert await app.call("rois.system.connect") == {"return_code": "OK"}
    result = await app.call("rois.command.search")
    assert result["component_ref_list"] == ["robot_1/SystemInformation", NAV]

    profile = (await app.call("rois.system.get_profile"))["profile"]
    assert profile["component_ids"] == ["robot_1/SystemInformation", NAV]
    nav = profile["component_profiles"][1]
    assert nav["function"] == "actuation"
    assert {c["name"] for c in nav["command_profiles"]} == {"set_parameter", "execute", "stop"}


async def test_query_and_command_through_the_gateway(stack) -> None:
    app, nav, _ = stack
    result = await app.call(
        "rois.query.query", component_ref="robot_1/SystemInformation", query_type="robot_position",
    )
    assert [r["name"] for r in result["results"]] == ["x", "y", "theta"]

    assert await app.code("rois.command.bind", component_ref=NAV) == "OK"
    code = await app.code("rois.command.set_parameter", component_ref=NAV, parameters=PARAMS)
    assert code == "OK"
    assert nav.parameters == PARAMS
    result = await app.call(
        "rois.command.execute", component_ref=NAV, command_type="execute", parameters=PARAMS,
    )
    assert result["return_code"] == "OK"
    assert result["command_id"] == "cmd-nav"
    assert nav.received == [PARAMS]
    assert await app.code("rois.command.release", component_ref=NAV) == "OK"


async def test_execute_without_binding_is_refused(stack) -> None:
    app, nav, _ = stack
    code = await app.code("rois.command.execute", component_ref=NAV, command_type="execute")
    assert code == "OUT_OF_RESOURCES"
    assert nav.received == []


async def test_events_flow_from_adapter_to_application(stack) -> None:
    app, nav, _ = stack
    result = await app.call("rois.event.subscribe", component_ref=NAV, event_type="reached_target")
    assert result["return_code"] == "OK"
    subscribe_id = result["subscribe_id"]
    assert nav.subscribed == 1

    await nav.arrive("kitchen")
    params = (await app.next_notification("rois.event.notify"))["params"]
    assert params["subscribe_id"] == subscribe_id
    assert params["component_ref"] == "Navigation"
    assert params["event_type"] == "reached_target"
    assert [r["name"] for r in params["results"]] == ["target", "is_final_target"]

    assert await app.code("rois.event.unsubscribe", subscribe_id=subscribe_id) == "OK"
    await nav.arrive("desk")
    # A later query still answers, and no stray event was queued before it.
    await app.call("rois.query.query", component_ref=NAV, query_type="component_status")
    assert not [n for n in app.notifications if n.get("method") == "rois.event.notify"]


async def test_client_disconnect_releases_bindings_and_subscriptions(stack) -> None:
    app, nav, gateway = stack
    port = app._ws.remote_address[1]
    async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
        other = Application(ws)
        assert await other.code("rois.command.bind", component_ref=NAV) == "OK"
        sub = await other.call(
            "rois.event.subscribe", component_ref=NAV, event_type="reached_target",
        )
        assert sub["return_code"] == "OK"
        assert await app.code("rois.command.bind", component_ref=NAV) == "OUT_OF_RESOURCES"
    # The other client is gone: its reservation is free and its subscription released upstream.
    for _ in range(50):
        if not gateway.get_bindings():
            break
        await asyncio.sleep(0.02)
    assert await app.code("rois.command.bind", component_ref=NAV) == "OK"
    await nav.arrive("kitchen")
    await app.call("rois.query.query", component_ref=NAV, query_type="component_status")
    assert not [n for n in app.notifications if n.get("method") == "rois.event.notify"]


async def test_completion_travels_from_adapter_to_application(stack) -> None:
    app, nav, _ = stack
    assert await app.code("rois.command.bind", component_ref=NAV) == "OK"
    executed = await app.call("rois.command.execute", component_ref=NAV, command_type="execute")
    assert executed["return_code"] == "OK"
    command_id = executed["command_id"]

    await nav.parent.complete_async(command_id, "OK", [])
    completed = await app.next_notification("rois.command.completed")
    assert completed["params"]["command_id"] == command_id
    assert completed["params"]["status"] == "OK"

    result = await app.call("rois.command.get_command_result", command_id=command_id)
    assert result["return_code"] == "OK"


async def test_component_failure_travels_as_notify_error(stack) -> None:
    app, _, _ = stack
    assert await app.code("rois.command.bind", component_ref=NAV) == "OK"
    failed = await app.call("rois.command.execute", component_ref=NAV, command_type="stop")
    assert failed["return_code"] == "ERROR"
    error = await app.next_notification("rois.system.notify_error")
    assert error["params"]["error_type"] == "COMPONENT_INTERNAL_ERROR"
    detail = await app.call("rois.system.get_error_detail", error_id=error["params"]["error_id"])
    assert detail["return_code"] == "OK"


async def test_bind_any_and_get_parameter_through_the_gateway(stack) -> None:
    app, nav, _ = stack
    bound = await app.call("rois.command.bind_any", condition="navigation")
    assert bound == {"return_code": "OK", "component_ref": NAV}
    code = await app.code("rois.command.set_parameter", component_ref=NAV, parameters=PARAMS)
    assert code == "OK"
    fetched = await app.call("rois.command.get_parameter", component_ref=NAV)
    assert fetched == {"return_code": "OK", "results": PARAMS}
