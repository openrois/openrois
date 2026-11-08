"""Tests of the MCP surface, through the MCP SDK's in-process client."""

from __future__ import annotations

import json
from typing import Any

from mcp import Client

from openrois.mcp.config import Settings
from openrois.mcp.server import build_server
from openrois.mcp.session import Session
from tests.fakes import Engine, factory_for

ACT_TOOLS = {"bind", "release", "set_parameters", "run_commands"}


def text(result: Any) -> str:
    return str(result.content[0].text)


async def test_read_only_by_default() -> None:
    server = build_server(Settings(), factory_for(Engine()))
    async with Client(server) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
    assert not names & ACT_TOOLS
    assert {"list_components", "describe_component", "query", "get_events"} <= names


async def test_actions_appear_with_their_annotations() -> None:
    server = build_server(Settings(allow_actions=True), factory_for(Engine()))
    async with Client(server) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert ACT_TOOLS <= set(tools)
    for name in ("run_commands", "set_parameters", "release"):
        annotations = tools[name].annotations
        assert annotations is not None and annotations.destructive_hint is True
    listed = tools["list_components"].annotations
    assert listed is not None and listed.read_only_hint is True


async def test_a_refusal_is_a_tool_error_the_agent_can_read() -> None:
    server = build_server(Settings(allow_actions=True), factory_for(Engine()))
    async with Client(server) as client:
        result = await client.call_tool(
            "run_commands",
            {"steps": [{"component_ref": "robot/navigation", "command_type": "start"}]},
        )
    assert result.is_error
    assert '"return_code": "NOT_BOUND"' in text(result)


async def test_resources_and_shutdown() -> None:
    engine = Engine()
    settings = Settings(allow_actions=True)
    session = Session(settings, factory_for(engine))
    server = build_server(settings, session=session)
    async with Client(server) as client:
        await client.call_tool("bind", {"ref": "robot/navigation"})
        component = await client.read_resource("rois://components/robot/navigation")
        described = json.loads(component.contents[0].text)  # type: ignore[union-attr]
        assert described["type"] == "OMG::Navigation"
        state = await client.read_resource("rois://session")
        assert json.loads(state.contents[0].text)["binds"] == [  # type: ignore[union-attr]
            "robot/navigation"
        ]
    # Leaving the client ends the server's lifespan, which releases and disconnects.
    assert engine.sessions[0].disconnected
    assert (1, "robot/navigation") in engine.released
