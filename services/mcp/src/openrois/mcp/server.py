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
   Right after subscribe, run_commands or set_parameters, wait_for_event starts at the
   cursor that call returned, so an event sent while a command ran is not missed. Any other
   wait waits for a fresh event. Some components, such as a person detector, send events only
   between their start and stop commands.
3. To act (when this server allows actions): bind a component, run_commands, then release.
   Many commands, such as a reaction or speech start, take no arguments and read the
   component's parameters instead: set them with set_parameters, or with a set_parameter
   step right before the command in run_commands. Parameters stay on the component between
   sessions, so set every parameter a command reads before each start: initial_value in
   describe_component is only the value before anyone set it.
4. An actuation component (one that moves, speaks or shows) takes one session at a time: a
   failed bind with OUT_OF_RESOURCES means another client holds it, and its status reads
   BUSY in list_components. Tell the user it is in use and ask before you wait for it.
5. release aborts this session's commands still running on the component. When the server
   closes, it stops what this session started and releases its binds.
6. A command that ends ERROR or ABORT comes with a hint and what the engine reported. A
   value the component refused often has a query, such as available_reactions, that lists
   the valid ones.

Values are plain JSON. The server types them from the component profile.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
ACTS = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
MOVES = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)

Ref = Annotated[str, Field(description="Fully qualified component ref, such as mock/navigation")]


def _with_notice(message: str, notice: str | None) -> str:
    """A tool error message that also carries a notice the agent has not heard yet."""
    if not notice:
        return message
    try:
        parsed = json.loads(message)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        parsed["notice"] = notice
        return json.dumps(parsed)
    return f"{message}\n\nNotice: {notice}"


async def _run(rois: Session, call: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    """Await a session call, turning the failures an agent can act on into tool errors.

    A failure carries the session's pending notice, such as a lost connection, so the
    agent hears it even when the call that follows the loss fails.
    """
    try:
        return await call
    except AgentError as exc:
        raise ToolError(_with_notice(str(exc), rois.take_notice())) from exc
    except TransportError as exc:
        message = (
            f"The gateway connection failed during the call: {exc}. The next call "
            "reconnects as a new session."
        )
        raise ToolError(_with_notice(message, rois.take_notice())) from exc


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
        return await _run(rois, rois.list_components(pattern))

    @server.tool(annotations=READ_ONLY)
    async def describe_component(ref: Ref) -> dict[str, Any]:
        """Show the commands, queries, events and parameters of one component, with types.

        A parameter's initial_value is its value before anyone set it. Parameters stay on
        the component between sessions, and value shows the current one while this session
        holds the component.
        """
        return await _run(rois, rois.describe_component(ref))

    @server.tool(annotations=READ_ONLY)
    async def query(
        ref: Ref,
        query_type: Annotated[str, Field(description="A query from describe_component")],
    ) -> dict[str, Any]:
        """Run a query on one component, such as component_status, and return its results."""
        return await _run(rois, rois.query(ref, query_type))

    @server.tool(annotations=READ_ONLY)
    async def get_parameters(ref: Ref) -> dict[str, Any]:
        """Read the current parameters of a component.

        An actuation component must be bound by this session first. Another component is
        bound for the read and released after, which a read-only server, or one whose
        --allow patterns exclude the component, does not do.
        """
        return await _run(rois, rois.get_parameters(ref))

    # -- Observe ------------------------------------------------------------

    @server.tool(annotations=ACTS)
    async def subscribe(
        ref: Ref,
        event_type: Annotated[str, Field(description="An event from describe_component")],
    ) -> dict[str, Any]:
        """Subscribe to an event of one component. Read occurrences with get_events.

        Some components send events only between their start and stop commands: the reply
        then has a hint. The next wait_for_event without since starts at the cursor this returns.
        """
        return await _run(rois, rois.subscribe(ref, event_type))

    @server.tool(annotations=ACTS)
    async def unsubscribe(subscribe_id: str) -> dict[str, Any]:
        """Cancel a subscription."""
        return await _run(rois, rois.unsubscribe(subscribe_id))

    @server.tool(annotations=READ_ONLY)
    async def get_events(
        since: Annotated[int, Field(description="Cursor from the last call. 0: oldest kept")] = 0,
        limit: Annotated[int, Field(ge=1, le=500)] = 50,
    ) -> dict[str, Any]:
        """Return the notifications after a cursor, and the cursor for the next call.

        Kinds: event, completed (a command ended), error, profile_changed (components joined
        or left), lost (binds and subscriptions the engine dropped), connection_closed,
        idle_release.
        """
        return rois.get_events(since, limit)

    @server.tool(annotations=READ_ONLY)
    async def wait_for_event(
        event_type: Annotated[str, Field(description="Only this event type. Empty: any")] = "",
        ref: Annotated[str, Field(description="Only from this component. Empty: any")] = "",
        timeout: Annotated[float, Field(gt=0, description="Seconds to wait")] = 30.0,
        since: Annotated[
            int | None,
            Field(
                description=(
                    "Match entries after this cursor, such as the cursor of the last wait to "
                    "read each entry in turn. Empty: right after subscribe, run_commands or "
                    "set_parameters, after the cursor that call returned; otherwise only "
                    "entries that arrive from now on"
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Wait until a matching event arrives, an error or a loss arrives, or the timeout passes.

        So that an event a component sends during a command is not missed, the first wait
        after subscribe, run_commands or set_parameters starts at the cursor that call
        returned. Any other wait without since waits for a fresh entry, not an old one.
        """
        return await rois.wait_for_event(event_type, ref, timeout, since)

    @server.tool(annotations=READ_ONLY)
    async def get_error_detail(error_id: str) -> dict[str, Any]:
        """Read the details of an error entry from get_events."""
        return await _run(rois, rois.get_error_detail(error_id))

    @server.tool(annotations=READ_ONLY)
    async def command_status(command_ids: list[str]) -> dict[str, Any]:
        """Return the status of commands this session ran, with results once they ended."""
        return await _run(rois, rois.command_status(command_ids))

    # -- Act ----------------------------------------------------------------

    if settings.allow_actions:

        @server.tool(annotations=ACTS)
        async def bind(
            ref: Ref,
            wait_seconds: Annotated[
                float,
                Field(
                    ge=0,
                    description=(
                        "Retry this long while another session holds it. Only after the user "
                        "agreed to wait"
                    ),
                ),
            ] = 0,
        ) -> dict[str, Any]:
            """Reserve a component for this session before commanding it.

            An actuation component takes one session at a time. OUT_OF_RESOURCES means
            another client holds it: tell the user and ask before waiting for it.
            """
            return await _run(rois, rois.bind(ref, wait_seconds))

        @server.tool(annotations=MOVES)
        async def release(ref: Ref) -> dict[str, Any]:
            """Free a component. This aborts this session's commands still running on it.

            aborted_command_ids are the commands that ended ABORT with the release.
            """
            return await _run(rois, rois.release(ref))

        @server.tool(annotations=MOVES)
        async def set_parameters(
            ref: Ref,
            values: Annotated[
                dict[str, Any], Field(description="Parameter name to plain JSON value")
            ],
            wait: bool = True,
        ) -> dict[str, Any]:
            """Set parameters of a bound component and wait until they apply."""
            return await _run(rois, rois.set_parameters(ref, values, wait))

        @server.tool(annotations=MOVES)
        async def run_commands(
            steps: Annotated[
                list[dict[str, Any]],
                Field(
                    description=(
                        "In order. A command: {component_ref, command_type, arguments?} with "
                        "arguments as name to plain JSON value. command_type set_parameter "
                        "takes parameter name to value, to set the parameters a following "
                        "command reads. A parallel group: {branch_list: [[command, ...], "
                        "...], delay_time?} whose branches run at the same time, each in "
                        "order, after delay_time ms"
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

            A command ends OK, ERROR, ABORT, TIMEOUT or OUT_OF_RESOURCES, with a hint when not
            OK. RUNNING means it had not ended when the wait did: follow it with
            command_status or get_events. CONNECTION_LOST means the gateway connection went
            during the wait, which ends the session and its commands.
            """
            return await _run(rois, rois.run_commands(steps, wait, timeout, auto_bind))

    # -- Resources ----------------------------------------------------------

    @server.resource(
        "rois://components",
        name="components",
        description="Every component with its type and what it offers",
        mime_type="application/json",
    )
    async def components_resource() -> str:
        try:
            client = await rois.client()
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
