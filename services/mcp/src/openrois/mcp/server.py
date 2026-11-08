"""The MCP tools and resources, each a thin call into the Session."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from openrois.sdk import TransportError
from pydantic import Field

from openrois.mcp import profiles
from openrois.mcp.config import AUTO_BIND_DEFAULT, Settings
from openrois.mcp.session import AgentError, ClientFactory, Session, connect_client

INSTRUCTIONS = """\
This server drives the physical robots, virtual avatars and AI services behind an OpenRoIS
gateway through the OMG RoIS Framework 2.0 interfaces.

1. list_components shows every component, its type, its status for this session and what
   it offers. describe_component gives the commands, queries, events and parameters of one.
2. query reads state. subscribe, then get_events or wait_for_event, follows what happens.
3. To act (when this server allows actions): bind a component, run_commands, then release.
   An actuation component (one that moves, speaks or shows) takes one session at a time:
   a failed bind with OUT_OF_RESOURCES means another session holds it. Its status reads
   BUSY in list_components. Try later, bind with wait_seconds, or pick another.
4. release aborts this session's commands still running on the component.

Values are plain JSON. The server types them from the component profile.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
ACTS = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
MOVES = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)

Ref = Annotated[str, Field(description="Fully qualified component ref, such as mock/navigation")]


async def _run(call: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    """Await a session call, turning the failures an agent can act on into tool errors."""
    try:
        return await call
    except AgentError as exc:
        raise ToolError(str(exc)) from exc
    except TransportError as exc:
        raise ToolError(
            f"The gateway connection failed during the call: {exc}. The next call "
            "reconnects as a new session."
        ) from exc


def build_server(
    settings: Settings,
    factory: ClientFactory = connect_client,
    session: Session | None = None,
) -> MCPServer[Any]:
    """An MCP server with one RoIS session, read-only unless settings.allow_actions.

    Args:
        settings: The gateway and the limits.
        factory: Opens the RoIS client. Tests pass a fake.
        session: An existing session to serve, for tests that inspect it.
    """
    rois = session or Session(settings, factory)

    @asynccontextmanager
    async def lifespan(_server: MCPServer[Any]) -> AsyncIterator[Session]:
        try:
            yield rois
        finally:
            await rois.shutdown()

    server: MCPServer[Any] = MCPServer(
        name="openrois",
        title="OpenRoIS",
        instructions=INSTRUCTIONS,
        lifespan=lifespan,
    )

    # -- Discover -----------------------------------------------------------

    @server.tool(annotations=READ_ONLY)
    async def list_components(
        pattern: Annotated[
            str, Field(description="CQL2 LIKE pattern on the ref, such as reachy_%. Empty: all")
        ] = "",
    ) -> dict[str, Any]:
        """List the components behind the gateway with their type, status and offers.

        component_status is what this session sees: BUSY means another session holds the
        component, null that the component declares no status. held_by_this_session tells
        whether this session has bound it.
        """
        return await _run(rois.list_components(pattern))

    @server.tool(annotations=READ_ONLY)
    async def describe_component(ref: Ref) -> dict[str, Any]:
        """Show the commands, queries, events and parameters of one component, with types."""
        return await _run(rois.describe_component(ref))

    @server.tool(annotations=READ_ONLY)
    async def query(
        ref: Ref,
        query_type: Annotated[str, Field(description="A query from describe_component")],
    ) -> dict[str, Any]:
        """Run a query on one component, such as component_status, and return its results."""
        return await _run(rois.query(ref, query_type))

    @server.tool(annotations=READ_ONLY)
    async def get_parameters(ref: Ref) -> dict[str, Any]:
        """Read the current parameters of a component.

        An actuation component must be bound by this session first.
        """
        return await _run(rois.get_parameters(ref))

    # -- Observe ------------------------------------------------------------

    @server.tool(annotations=ACTS)
    async def subscribe(
        ref: Ref,
        event_type: Annotated[str, Field(description="An event from describe_component")],
    ) -> dict[str, Any]:
        """Subscribe to an event of one component. Read occurrences with get_events."""
        return await _run(rois.subscribe(ref, event_type))

    @server.tool(annotations=ACTS)
    async def unsubscribe(subscribe_id: str) -> dict[str, Any]:
        """Cancel a subscription."""
        return await _run(rois.unsubscribe(subscribe_id))

    @server.tool(annotations=READ_ONLY)
    async def get_events(
        since: Annotated[int, Field(description="Cursor from the last call. 0: oldest kept")] = 0,
        limit: Annotated[int, Field(ge=1, le=500)] = 50,
    ) -> dict[str, Any]:
        """Return the notifications after a cursor, and the cursor for the next call.

        Kinds: event, completed (a command ended), error, profile_changed (components joined
        or left), connection_closed, idle_release.
        """
        return rois.get_events(since, limit)

    @server.tool(annotations=READ_ONLY)
    async def wait_for_event(
        event_type: Annotated[str, Field(description="Only this event type. Empty: any")] = "",
        ref: Annotated[str, Field(description="Only from this component. Empty: any")] = "",
        timeout: Annotated[float, Field(gt=0, description="Seconds to wait")] = 30.0,
        since: Annotated[
            int | None, Field(description="Also match entries after this cursor")
        ] = None,
    ) -> dict[str, Any]:
        """Wait until a matching event arrives, an error arrives, or the timeout passes."""
        return await rois.wait_for_event(event_type, ref, timeout, since)

    @server.tool(annotations=READ_ONLY)
    async def get_error_detail(error_id: str) -> dict[str, Any]:
        """Read the details of an error entry from get_events."""
        return await _run(rois.get_error_detail(error_id))

    @server.tool(annotations=READ_ONLY)
    async def command_status(command_ids: list[str]) -> dict[str, Any]:
        """Return the status of commands this session ran, with results once they ended."""
        return await _run(rois.command_status(command_ids))

    # -- Act ----------------------------------------------------------------

    if settings.allow_actions:

        @server.tool(annotations=ACTS)
        async def bind(
            ref: Ref,
            wait_seconds: Annotated[
                float, Field(ge=0, description="Retry this long while another session holds it")
            ] = 0,
        ) -> dict[str, Any]:
            """Reserve a component for this session before commanding it.

            An actuation component takes one session at a time. OUT_OF_RESOURCES means
            another session holds it.
            """
            return await _run(rois.bind(ref, wait_seconds))

        @server.tool(annotations=MOVES)
        async def release(ref: Ref) -> dict[str, Any]:
            """Free a component. This aborts this session's commands still running on it."""
            return await _run(rois.release(ref))

        @server.tool(annotations=MOVES)
        async def set_parameters(
            ref: Ref,
            values: Annotated[
                dict[str, Any], Field(description="Parameter name to plain JSON value")
            ],
            wait: bool = True,
        ) -> dict[str, Any]:
            """Set parameters of a bound component and wait until they apply."""
            return await _run(rois.set_parameters(ref, values, wait))

        @server.tool(annotations=MOVES)
        async def run_commands(
            steps: Annotated[
                list[dict[str, Any]],
                Field(
                    description=(
                        "In order. A command: {component_ref, command_type, arguments?} with "
                        "arguments as name to plain JSON value. A parallel group: "
                        "{branch_list: [[command, ...], ...], delay_time?} whose branches run "
                        "at the same time, each in order, after delay_time ms"
                    )
                ),
            ],
            wait: Annotated[
                bool, Field(description="Wait for every command to end and return statuses")
            ] = True,
            timeout: Annotated[
                float | None, Field(gt=0, description="Seconds to wait, capped by the server")
            ] = None,
            auto_bind: Annotated[
                bool,
                Field(
                    description=(
                        "Bind the components first, all or nothing. Off: every component "
                        "must already be bound by this session"
                    )
                ),
            ] = AUTO_BIND_DEFAULT,
        ) -> dict[str, Any]:
            """Run commands on bound components and report how each ended.

            A command ends OK, ERROR, ABORT, TIMEOUT or OUT_OF_RESOURCES. RUNNING means it
            had not ended when the wait did: follow it with command_status or get_events.
            """
            return await _run(rois.run_commands(steps, wait, timeout, auto_bind))

    # -- Resources ----------------------------------------------------------

    @server.resource(
        "rois://components",
        name="components",
        description="Every component with its type and what it offers",
        mime_type="application/json",
    )
    async def components_resource() -> str:
        try:
            client, _ = await rois.client()
            engine = await client.get_profile("")
        except (AgentError, TransportError) as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(
            [profiles.summary(ref, p) for ref, p in sorted(engine.component_profiles.items())]
        )

    @server.resource(
        "rois://components/{+ref}",
        name="component",
        description="The profile of one component, condensed for an agent",
        mime_type="application/json",
    )
    async def component_resource(ref: str) -> str:
        try:
            return json.dumps(profiles.describe(ref, await rois.profile_of(ref)))
        except (AgentError, TransportError) as exc:
            return json.dumps({"error": str(exc)})

    @server.resource(
        "rois://session",
        name="session",
        description="This session's binds, subscriptions, running commands and connection",
        mime_type="application/json",
    )
    async def session_resource() -> str:
        return json.dumps(rois.state())

    return server
