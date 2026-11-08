"""The server against a live gateway with the mock adapter, through the MCP client.

Skipped unless OPENROIS_GATEWAY_URL names the gateway, for example after
``docker compose up --build -d`` at the repository root:

    OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 pytest tests/integration

The mock adapter serves mock/navigation (actuation), mock/person_detection (sensing)
and mock/system_information.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from typing import Any

import pytest
from mcp import Client, ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openrois.mcp.config import Settings
from openrois.mcp.server import build_server

URL = os.environ.get("OPENROIS_GATEWAY_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="OPENROIS_GATEWAY_URL is not set")

NAV = "mock/navigation"
PEOPLE = "mock/person_detection"


def agent() -> Client:
    """A client on a server of its own, so it has a RoIS session of its own."""
    return Client(build_server(Settings(gateway_url=URL, allow_actions=True, command_timeout=30)))


async def call(client: Client, tool: str, **arguments: Any) -> dict[str, Any]:
    result = await client.call_tool(tool, arguments)
    assert not result.is_error, result.content[0].text  # type: ignore[union-attr]
    parsed: dict[str, Any] = json.loads(result.content[0].text)  # type: ignore[union-attr]
    return parsed


async def refused(client: Client, tool: str, **arguments: Any) -> str:
    result = await client.call_tool(tool, arguments)
    assert result.is_error
    return str(result.content[0].text)  # type: ignore[union-attr]


async def test_discover_the_mock_components() -> None:
    async with agent() as client:
        listed = await call(client, "list_components")
        refs = {component["ref"] for component in listed["components"]}
        assert {NAV, PEOPLE, "mock/system_information"} <= refs
        described = await call(client, "describe_component", ref=NAV)
        assert described["needs_exclusive_bind"] is True
        assert "target_positions" in {p["name"] for p in described["parameters"]}
        position = await call(
            client, "query", ref="mock/system_information", query_type="robot_position"
        )
        assert position["results"]


async def test_navigate_with_an_explicit_bind() -> None:
    async with agent() as client:
        message = await refused(
            client, "run_commands", steps=[{"component_ref": NAV, "command_type": "start"}]
        )
        assert '"return_code": "NOT_BOUND"' in message
        await call(client, "bind", ref=NAV)
        changed = await call(
            client, "set_parameters", ref=NAV, values={"target_positions": ["kitchen"]}
        )
        assert changed["status"] == "OK"
        ran = await call(
            client, "run_commands", steps=[{"component_ref": NAV, "command_type": "start"}]
        )
        assert ran["commands"][0]["status"] == "OK"
        await call(client, "release", ref=NAV)


async def test_two_agents_compete_for_an_actuation_component() -> None:
    async with agent() as first, agent() as second:
        await call(first, "bind", ref=NAV)

        message = await refused(second, "bind", ref=NAV)
        # The MCP SDK puts "Error executing tool bind: " before the JSON of the refusal.
        failure = json.loads(message[message.index("{") :])
        assert failure["return_code"] == "OUT_OF_RESOURCES"
        assert failure["component_ref"] == NAV
        assert "another session holds this component" in failure["hint"]

        auto = await refused(
            second,
            "run_commands",
            steps=[{"component_ref": NAV, "command_type": "start"}],
            auto_bind=True,
        )
        assert '"return_code": "OUT_OF_RESOURCES"' in auto

        seen = await call(second, "list_components", pattern="mock/nav%")
        assert seen["components"][0]["component_status"] == "BUSY"
        assert seen["components"][0]["held_by_this_session"] is False

        await call(first, "release", ref=NAV)
        bound = await call(second, "bind", ref=NAV, wait_seconds=5)
        assert bound["bound"] is True

        # A sensing component takes a bind per session, so both hold it at once.
        await call(first, "bind", ref=PEOPLE)
        await call(second, "bind", ref=PEOPLE)


async def test_follow_person_detection_events() -> None:
    async with agent() as client:
        subscribed = await call(client, "subscribe", ref=PEOPLE, event_type="person_detected")
        waited = await call(
            client, "wait_for_event", event_type="person_detected", ref=PEOPLE, timeout=20
        )
        assert waited["timed_out"] is False
        assert waited["entry"]["subscribe_id"] == subscribed["subscribe_id"]
        read = await call(client, "get_events", since=subscribed["cursor"])
        assert any(entry["kind"] == "event" for entry in read["entries"])
        await call(client, "unsubscribe", subscribe_id=subscribed["subscribe_id"])


async def test_leaving_releases_the_binds() -> None:
    async with agent() as first:
        await call(first, "bind", ref=NAV)
    async with agent() as second:
        bound = await call(second, "bind", ref=NAV)
        assert bound["bound"] is True


FAULT = "mock/fault"


async def test_parameters_set_in_the_same_run_as_the_command() -> None:
    async with agent() as client:
        ran = await call(
            client,
            "run_commands",
            steps=[
                {
                    "component_ref": NAV,
                    "command_type": "set_parameter",
                    "arguments": {"target_positions": ["hall"]},
                },
                {"component_ref": NAV, "command_type": "start"},
            ],
            auto_bind=True,
        )
        assert [command["status"] for command in ran["commands"]] == ["OK", "OK"]
        read = await call(client, "get_parameters", ref=NAV)
        values = {item["name"]: item["value"] for item in read["parameters"]}
        assert values["target_positions"] == ["hall"]


async def test_an_event_sent_during_a_command_reaches_the_wait_after_it() -> None:
    async with agent() as client:
        await call(client, "subscribe", ref=FAULT, event_type="echoed")
        # echo sends echoed before it completes, so the event is in before the wait starts.
        await call(
            client,
            "run_commands",
            steps=[{"component_ref": FAULT, "command_type": "echo", "arguments": {"text": "hi"}}],
            auto_bind=True,
        )
        waited = await call(client, "wait_for_event", event_type="echoed", timeout=5)
        assert waited["timed_out"] is False


async def test_a_command_after_a_failed_one_says_why_it_ended() -> None:
    async with agent() as client:
        ran = await call(
            client,
            "run_commands",
            steps=[
                {
                    "component_ref": FAULT,
                    "command_type": "end_with",
                    "arguments": {"status": "ERROR"},
                },
                {"component_ref": FAULT, "command_type": "echo", "arguments": {"text": "x"}},
            ],
            auto_bind=True,
        )
        failed, skipped = ran["commands"]
        assert failed["status"] == "ERROR" and "RoIS carries no reason" in failed["hint"]
        assert skipped["status"] == "ABORT"
        assert failed["command_id"] in skipped["hint"]


async def test_release_reports_as_aborted_only_what_ended_abort() -> None:
    async with agent() as client:
        await call(client, "bind", ref=NAV)
        await call(client, "bind", ref=FAULT)
        await call(client, "set_parameters", ref=NAV, values={"target_positions": ["kitchen"]})
        started = await call(
            client,
            "run_commands",
            steps=[
                {"component_ref": NAV, "command_type": "start"},
                {"component_ref": FAULT, "command_type": "echo", "arguments": {"text": "x"}},
            ],
            wait=False,
        )
        released = await call(client, "release", ref=FAULT)
        ended = await call(client, "command_status", command_ids=started["command_ids"])
        status = {command["command_id"]: command["status"] for command in ended["commands"]}
        for command_id in released.get("aborted_command_ids", []):
            assert status[command_id] == "ABORT"


async def test_a_profile_change_that_drops_nothing_keeps_the_binds() -> None:
    async with agent() as client:
        await call(client, "bind", ref=NAV)
        await call(client, "subscribe", ref=PEOPLE, event_type="person_detected")
        # peer_join makes a second engine join the gateway and leave it again.
        await call(
            client,
            "run_commands",
            steps=[{"component_ref": FAULT, "command_type": "peer_join"}],
            auto_bind=True,
        )
        ran = await call(
            client, "run_commands", steps=[{"component_ref": NAV, "command_type": "stop"}]
        )
        assert ran["commands"][0]["status"] == "OK"
        listed = await call(client, "list_components", pattern="mock/nav%")
        assert listed["components"][0]["held_by_this_session"] is True
        read = await call(client, "get_events", since=0, limit=500)
        kinds = {entry["kind"] for entry in read["entries"]}
        assert "profile_changed" in kinds and "lost" not in kinds


async def test_the_console_script_serves_over_stdio() -> None:
    command = shutil.which("openrois-mcp") or os.path.join(
        os.path.dirname(sys.executable), "openrois-mcp"
    )
    server = StdioServerParameters(
        command=command, args=["--gateway-url", URL], env=dict(os.environ)
    )
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        names = {tool.name for tool in (await session.list_tools()).tools}
        # Read-only without --allow-actions.
        assert "list_components" in names and "run_commands" not in names
        result = await session.call_tool("list_components", {})
        assert not result.is_error
        listed = json.loads(result.content[0].text)  # type: ignore[union-attr]
        assert NAV in {component["ref"] for component in listed["components"]}
