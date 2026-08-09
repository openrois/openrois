"""Tests for the AdapterFramework."""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets
from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import ReturnCode

from openrois.sdk import RobotAdapter, component, invoke, query, results, subscribe
from openrois.sdk.framework import AdapterFramework


class MockAdapter(RobotAdapter):
    """Mock adapter with two components for framework testing."""

    def __init__(self, config: dict) -> None:
        self.query_called: list[str] = []
        self.invoke_called: list[str] = []
        self.subscribe_called: list[str] = []
        super().__init__(config)

    @component("SystemInformation", bind_required=False)
    class SystemInformation:
        @query("robot_position")
        async def robot_position(self):
            self.parent.query_called.append("robot_position")
            return results.position(x=1.0, y=2.0, theta=0.5)

        @query("component_status")
        async def status(self):
            return results.status("READY")

    @component("Navigation", bind_required=True)
    class Navigation:
        @query("waypoints")
        async def get_waypoints(self):
            return results.waypoints([
                {"id": "desk", "name": "desk", "x": 2.0, "y": 1.5},
            ])

        @invoke("execute")
        async def navigate(self, parameters):
            self.parent.invoke_called.append("execute")
            return InvokeResponse(
                return_code=ReturnCode.OK,
                command_id="cmd-test",
            )

        @invoke("stop")
        async def stop(self, parameters):
            self.parent.invoke_called.append("stop")
            return InvokeResponse(return_code=ReturnCode.OK, command_id="")

        @subscribe("reached_target")
        async def on_reached(self):
            self.parent.subscribe_called.append("reached_target")


class AvatarServer:
    """Mock avatar WS server for testing.

    The handler loop receives messages from the adapter and stores them.
    The test sends requests via send() and reads responses from a queue.
    """

    def __init__(self) -> None:
        self.received: list[dict] = []
        self._ws: websockets.WebSocketServerProtocol | None = None
        self._responses: asyncio.Queue[dict] = asyncio.Queue()

    async def handler(self, ws: websockets.WebSocketServerProtocol) -> None:
        self._ws = ws
        try:
            async for raw in ws:
                msg = json.loads(raw)
                # Registration: auto-respond.
                if msg.get("method") == "rois.adapter.register":
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "id": msg["id"],
                        "result": {"return_code": "OK"},
                    }))
                    self.received.append(msg)
                # Response to a request we sent (has id, no method).
                elif "id" in msg and "method" not in msg:
                    await self._responses.put(msg)
                # Notification from the adapter (has method, no id).
                elif "method" in msg and "id" not in msg:
                    await self._responses.put(msg)
                else:
                    self.received.append(msg)
        except websockets.ConnectionClosed:
            pass

    async def send(self, msg: dict) -> None:
        """Send a request from the avatar to the adapter."""
        if self._ws:
            await self._ws.send(json.dumps(msg))

    async def recv_response(self, timeout: float = 2.0) -> dict:
        """Receive a response or notification from the adapter."""
        return await asyncio.wait_for(self._responses.get(), timeout=timeout)


@pytest.fixture
async def avatar_and_adapter():
    """Start a mock avatar server and connect a framework to it.

    Yields (avatar_server, adapter, framework) after registration.
    """
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    avatar = AvatarServer()
    server = await websockets.serve(avatar.handler, "127.0.0.1", port)

    config = {
        "fleet_id": "test_robot",
        "connection": {"ws": {"host": "127.0.0.1", "port": port}},
    }
    adapter = MockAdapter(config)
    framework = AdapterFramework(adapter, config)

    task = asyncio.create_task(framework._run_async())
    # Wait for registration to complete.
    await asyncio.sleep(0.3)

    assert len(avatar.received) >= 1
    assert avatar.received[0]["method"] == "rois.adapter.register"

    yield avatar, adapter, framework

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    server.close()
    await server.wait_closed()


async def test_framework_connects_and_registers(avatar_and_adapter):
    """The framework connects to the avatar and sends registration."""
    avatar, adapter, framework = avatar_and_adapter
    assert framework._ws is not None
    reg_msg = avatar.received[0]
    assert reg_msg["method"] == "rois.adapter.register"
    assert reg_msg["params"]["fleet_id"] == "test_robot"
    refs = [c["ref"] for c in reg_msg["params"]["components"]]
    assert "SystemInformation" in refs
    assert "Navigation" in refs


async def test_framework_dispatches_query(avatar_and_adapter):
    """The framework dispatches rois.query.query to the @query handler."""
    avatar, adapter, framework = avatar_and_adapter
    await avatar.send({
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "rois.query.query",
        "params": {
            "component_ref": "test_robot/SystemInformation",
            "query_type": "robot_position",
        },
    })
    response = await avatar.recv_response()
    assert response["id"] == "req-1"
    assert response["result"]["return_code"] == "OK"
    assert len(response["result"]["results"]) == 3
    assert response["result"]["results"][0]["name"] == "x"
    assert "robot_position" in adapter.query_called


async def test_framework_dispatches_invoke(avatar_and_adapter):
    """The framework dispatches rois.command.execute to the @invoke handler."""
    avatar, adapter, framework = avatar_and_adapter
    await avatar.send({
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "rois.command.execute",
        "params": {
            "component_ref": "test_robot/Navigation",
            "command_unit_list": [
                {
                    "component_ref": "test_robot/Navigation",
                    "command_type": "execute",
                    "command_id": "cmd-2",
                    "arguments": [],
                },
            ],
        },
    })
    response = await avatar.recv_response()
    assert response["id"] == "req-2"
    assert response["result"]["return_code"] == "OK"
    assert response["result"]["command_id"] == "cmd-test"
    assert "execute" in adapter.invoke_called


async def test_framework_dispatches_subscribe(avatar_and_adapter):
    """The framework dispatches rois.event.subscribe to the @subscribe handler."""
    avatar, adapter, framework = avatar_and_adapter
    await avatar.send({
        "jsonrpc": "2.0",
        "id": "req-3",
        "method": "rois.event.subscribe",
        "params": {
            "component_ref": "test_robot/Navigation",
            "event_type": "reached_target",
        },
    })
    response = await avatar.recv_response()
    assert response["id"] == "req-3"
    assert response["result"]["return_code"] == "OK"
    assert response["result"]["subscribe_id"].startswith("sub-")
    assert "reached_target" in adapter.subscribe_called


async def test_framework_returns_unsupported_for_unknown_component(avatar_and_adapter):
    """The framework returns UNSUPPORTED for an unknown component ref."""
    avatar, adapter, framework = avatar_and_adapter
    await avatar.send({
        "jsonrpc": "2.0",
        "id": "req-4",
        "method": "rois.query.query",
        "params": {
            "component_ref": "test_robot/Unknown",
            "query_type": "something",
        },
    })
    response = await avatar.recv_response()
    assert response["result"]["return_code"] == "UNSUPPORTED"


async def test_framework_get_profile_returns_component_metadata(avatar_and_adapter):
    """get_profile returns component_ids and capability profiles."""
    avatar, adapter, framework = avatar_and_adapter
    await avatar.send({
        "jsonrpc": "2.0",
        "id": "req-profile",
        "method": "rois.system.get_profile",
        "params": {},
    })
    response = await avatar.recv_response()
    assert response["id"] == "req-profile"
    result = response["result"]
    assert result["return_code"] == "OK"

    # The profile is wrapped under a "profile" key with an identifier.
    profile = result["profile"]
    assert profile["identifier"]["code"] == "test_robot"

    # component_ids have the fleet_id prefix.
    ids = profile["component_ids"]
    assert "test_robot/SystemInformation" in ids
    assert "test_robot/Navigation" in ids

    # Find the Navigation profile and check its capabilities.
    nav_idx = ids.index("test_robot/Navigation")
    nav_profile = profile["component_profiles"][nav_idx]

    query_names = [q["name"] for q in nav_profile["query_profiles"]]
    assert "waypoints" in query_names

    cmd_names = [c["name"] for c in nav_profile["command_profiles"]]
    assert "execute" in cmd_names
    assert "stop" in cmd_names

    event_names = [e["name"] for e in nav_profile["event_profiles"]]
    assert "reached_target" in event_names

    # SystemInformation has robot_position but no commands or events.
    sys_idx = ids.index("test_robot/SystemInformation")
    sys_profile = profile["component_profiles"][sys_idx]

    sys_query_names = [q["name"] for q in sys_profile["query_profiles"]]
    assert "robot_position" in sys_query_names
    assert sys_profile["command_profiles"] == []
    assert sys_profile["event_profiles"] == []


async def test_framework_emit_sends_notification(avatar_and_adapter):
    """emit() sends an event notification to the avatar."""
    avatar, adapter, framework = avatar_and_adapter

    # Subscribe first so emit has a target.
    await avatar.send({
        "jsonrpc": "2.0",
        "id": "req-5",
        "method": "rois.event.subscribe",
        "params": {
            "component_ref": "test_robot/Navigation",
            "event_type": "reached_target",
        },
    })
    await avatar.recv_response()  # subscribe response

    # Emit an event from the adapter.
    adapter.emit(  # type: ignore[attr-defined]
        "Navigation",
        "reached_target",
        results.reached_target(target="desk", is_final_target=True),
    )
    await asyncio.sleep(0.1)

    # The notification should arrive at the avatar.
    notification = await avatar.recv_response()
    assert notification["method"] == "rois.event.notify"
    assert notification["params"]["event_type"] == "reached_target"
    assert "event_id" in notification["params"]
    assert notification["params"]["component_ref"] == "Navigation"
    assert notification["params"]["expire"] == ""
