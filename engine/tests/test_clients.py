"""Clients: the JSON-RPC envelope, concurrency, events and disconnect cleanup."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import pytest
from openrois_components_core import results
from websockets.asyncio.client import connect

from openrois.engine import WsServer
from tests._support import Adapter, Gateway, RpcClient, wait_until

NAVIGATION = "robot/Navigation"


async def roundtrip(gateway: Gateway, payload: str) -> dict[str, Any]:
    """Send one raw message as a client and return the parsed reply."""
    async with connect(gateway.url) as connection:
        await connection.send(payload)
        reply: dict[str, Any] = json.loads(await connection.recv())
        return reply


# ---------------------------------------------------------------------------
# JSON-RPC envelope
# ---------------------------------------------------------------------------


async def test_json_that_does_not_parse_is_a_parse_error(gateway: Gateway) -> None:
    reply = await roundtrip(gateway, "{not json")
    assert reply["id"] is None
    assert reply["error"]["code"] == -32700


@pytest.mark.parametrize(
    ("payload", "expected_id"),
    [
        ("[]", None),
        ('"text"', None),
        ('{"jsonrpc": "1.0", "id": 7, "method": "rois.system.connect"}', 7),
        ('{"jsonrpc": "2.0", "id": "r1", "method": 42}', "r1"),
        ('{"jsonrpc": "2.0", "id": true, "method": "rois.system.connect"}', None),
        ('{"jsonrpc": "2.0", "id": 3}', 3),
    ],
)
async def test_an_object_that_is_not_a_request_is_an_invalid_request(
    gateway: Gateway, payload: str, expected_id: object
) -> None:
    reply = await roundtrip(gateway, payload)
    assert reply["id"] == expected_id
    assert reply["error"]["code"] == -32600


async def test_positional_params_are_invalid_params(gateway: Gateway) -> None:
    payload = '{"jsonrpc": "2.0", "id": 1, "method": "rois.system.connect", "params": []}'
    reply = await roundtrip(gateway, payload)
    assert reply["error"]["code"] == -32602


async def test_a_notification_gets_no_reply(gateway: Gateway) -> None:
    async with connect(gateway.url) as connection:
        await connection.send('{"jsonrpc": "2.0", "method": "rois.system.connect"}')
        await connection.send('{"jsonrpc": "2.0", "id": "after", "method": "rois.system.connect"}')
        reply = json.loads(await connection.recv())
    assert reply["id"] == "after"


async def test_an_engine_failure_is_an_internal_error(
    gateway: Gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*args: object) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(gateway.engine, "dispatch", fail)
    reply = await roundtrip(gateway, '{"jsonrpc": "2.0", "id": 1, "method": "rois.system.connect"}')
    assert reply == {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32603, "message": "Internal error"},
    }


# ---------------------------------------------------------------------------
# Requests through the gateway to an adapter
# ---------------------------------------------------------------------------


async def test_a_slow_command_leaves_other_requests_unblocked(
    adapter: Adapter, client: RpcClient
) -> None:
    bound = await client.call("rois.command.bind", {"component_ref": NAVIGATION})
    assert bound["return_code"] == "OK"
    hold = client.send(
        "rois.command.execute", {"component_ref": NAVIGATION, "command_type": "hold"}
    )

    status = await client.call(
        "rois.query.query", {"component_ref": NAVIGATION, "query_type": "component_status"}
    )
    assert status["return_code"] == "OK"
    assert not hold.done()

    adapter.navigation.release_hold.set()
    reply = await asyncio.wait_for(hold, timeout=2.0)
    assert reply["result"]["return_code"] == "OK"


async def test_a_child_that_stops_replying_times_out(adapter: Adapter, client: RpcClient) -> None:
    await client.call("rois.command.bind", {"component_ref": NAVIGATION})
    result = await client.call(
        "rois.command.execute", {"component_ref": NAVIGATION, "command_type": "hold"}
    )
    assert result["return_code"] == "TIMEOUT"
    adapter.navigation.release_hold.set()


async def test_adapter_events_reach_the_client_that_subscribed(
    adapter: Adapter, client: RpcClient
) -> None:
    subscribed = await client.call(
        "rois.event.subscribe", {"component_ref": NAVIGATION, "event_type": "reached_target"}
    )
    assert subscribed["return_code"] == "OK"

    await adapter.navigation.parent.emit_async(  # type: ignore[attr-defined]
        "Navigation", "reached_target", results.reached_target("kitchen", True)
    )

    event = await client.notification("rois.event.notify")
    assert event["subscribe_id"] == subscribed["subscribe_id"]
    assert event["event_type"] == "reached_target"
    assert event["results"][0] == {"name": "target", "data_type_ref": "string", "value": "kitchen"}


async def test_events_emitted_from_another_thread_reach_the_client(
    adapter: Adapter, client: RpcClient
) -> None:
    await client.call(
        "rois.event.subscribe", {"component_ref": NAVIGATION, "event_type": "reached_target"}
    )

    def emit_from_thread() -> None:
        adapter.navigation.parent.emit(  # type: ignore[attr-defined]
            "Navigation", "reached_target", results.reached_target("dock", True)
        )

    thread = threading.Thread(target=emit_from_thread)
    thread.start()
    thread.join()

    event = await client.notification("rois.event.notify")
    assert event["results"][0]["value"] == "dock"


async def test_events_go_only_to_the_client_that_subscribed(
    gateway: Gateway, adapter: Adapter, client: RpcClient
) -> None:
    other = await RpcClient.connect(gateway.url)
    try:
        await client.call(
            "rois.event.subscribe", {"component_ref": NAVIGATION, "event_type": "reached_target"}
        )
        await adapter.navigation.parent.emit_async(  # type: ignore[attr-defined]
            "Navigation", "reached_target", results.reached_target("kitchen", True)
        )
        await client.notification("rois.event.notify")
        with pytest.raises(TimeoutError):
            await other.notification("rois.event.notify", timeout=0.2)
    finally:
        await other.close()


# ---------------------------------------------------------------------------
# Disconnect cleanup
# ---------------------------------------------------------------------------


async def test_a_disconnected_client_releases_its_bindings_and_subscriptions(
    gateway: Gateway, adapter: Adapter
) -> None:
    rpc = await RpcClient.connect(gateway.url)
    await rpc.call("rois.command.bind", {"component_ref": NAVIGATION})
    await rpc.call(
        "rois.event.subscribe", {"component_ref": NAVIGATION, "event_type": "reached_target"}
    )
    emitter = adapter.engine.component_registry._emitter
    assert emitter is not None
    assert emitter.has_subscribers("Navigation", "reached_target")

    await rpc.close()

    await wait_until(lambda: gateway.engine.get_bindings() == [])
    await wait_until(lambda: not emitter.has_subscribers("Navigation", "reached_target"))


async def test_stopping_the_server_closes_clients_with_going_away(gateway: Gateway) -> None:
    async with connect(gateway.url) as connection:
        await gateway.server.stop()
        await asyncio.wait_for(connection.wait_closed(), timeout=2.0)
        assert connection.close_code == 1001


def test_the_port_is_unknown_before_the_server_starts() -> None:
    from openrois.engine import Engine

    with pytest.raises(RuntimeError):
        _ = WsServer(Engine()).port
