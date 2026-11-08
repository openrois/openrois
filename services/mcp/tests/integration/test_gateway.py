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
from typing import Any

import pytest
from mcp import Client

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
