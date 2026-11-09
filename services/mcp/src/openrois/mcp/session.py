"""One RoIS session for one agent, and what the tools do with it.

The engine tells clients apart by their session: it gives an actuation component to one
session at a time, sends a command's completion to the session that ran it, and drops a
session's binds and subscriptions when it goes. So one server process holds one session,
opened on the first tool call, and every agent should run its own server.

Errors an agent can act on raise AgentError with a message written for the agent. The
server turns it into an MCP tool error.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from openrois.interfaces import (
    CompletedParams,
    HRIComponentProfile,
    NotifyErrorParams,
    NotifyEventParams,
    Parameter,
    ProfileChangedParams,
    Result,
    ReturnCode,
)
from openrois.interfaces.profiles import ComponentFunction
from openrois.sdk import (
    COMPONENT_REF,
    EngineProfile,
    RoISClient,
    RoISError,
    TransportError,
    component_ref,
    like,
)

from openrois.mcp import profiles, values
from openrois.mcp.allow import AllowFilter
from openrois.mcp.config import AUTO_BIND_DEFAULT, Settings
from openrois.mcp.events import Entry, EventBuffer

logger = logging.getLogger("openrois.mcp")

#: How often bind retries while it waits for a busy component, in seconds.
BIND_RETRY_INTERVAL = 0.5

#: How long release waits for the engine to end the commands it aborts, in seconds.
RELEASE_SETTLE = 1.0

#: The longest shutdown spends stopping, unsubscribing and releasing, in seconds. The
#: disconnect after it ends whatever is left with the session.
SHUTDOWN_TIMEOUT = 5.0

#: What an agent can do about each return code.
HINTS: dict[str, str] = {
    "OUT_OF_RESOURCES": (
        "another session holds this component: another agent, application or workflow "
        "connected to the gateway, and RoIS does not say which. Tell the user that the "
        "component is in use by another client and ask whether to wait for it, try later or "
        "use another component. Call bind with wait_seconds only after the user agreed to wait"
    ),
    "BAD_PARAMETER": "a name or value does not match the profile, see describe_component",
    "UNSUPPORTED": "the component does not declare this, see describe_component",
    "ERROR": "the engine refused the call",
    "TIMEOUT": "the component did not answer in time",
    "NOT_BOUND": "not bound by this session, call bind first",
    "NOT_ALLOWED": "this server was started with --allow patterns that exclude the component",
}

#: The hint of an ERROR from a query or a subscribe, which never need a bind.
NOT_OPERABLE = (
    "the component cannot serve this now: its device or adapter may be unreachable, asleep "
    "or in error. Look at component_status in list_components, where the component declares "
    "it, and at the error entries in get_events, and tell the user"
)

#: The hint of an ERROR from a command operation by a session that holds no bind.
NEEDS_BIND = "a command operation needs a bind by this session on the component, call bind first"

#: The hint of an ERROR from a command operation on a component this session had bound.
BIND_DROPPED = (
    "the engine no longer holds this session's bind on the component, for example because "
    "the component's engine reconnected to the gateway. Call bind again, then set its "
    "parameters and run the commands again"
)

#: The command operations, which answer ERROR when the session holds no bind.
COMMAND_METHODS = frozenset(
    {"rois.command.execute", "rois.command.set_parameter", "rois.command.get_parameter"}
)

#: What a command that ended other than OK tells the agent.
STATUS_HINTS: dict[str, str] = {
    "ERROR": (
        "the command failed on the component, and RoIS carries no reason. component_status "
        "and errors, when present, are what the engine reported (get_error_detail reads an "
        "error). Tell the user rather than retrying the same input"
    ),
    "ABORT": (
        "the command ended early: an earlier command in its sequence failed, or a stop, a "
        "release, a new start or the end of the session cut it short"
    ),
    "TIMEOUT": "the component did not finish the command in its time limit",
    "CONNECTION_LOST": (
        "the gateway connection was lost while the command ran, and the engine aborted it "
        "with the session. The next call opens a new session: bind again before running it"
    ),
}

#: The status of a command still running when a wait ends.
RUNNING = "RUNNING"

#: The status of a command whose wait ended because the gateway connection was lost.
CONNECTION_LOST = "CONNECTION_LOST"

#: The notice of a lost gateway connection, until a tool response delivers it.
CONNECTION_LOST_NOTICE = (
    "The connection to the gateway was lost, and the engine ended this session with it: its "
    "binds, subscriptions and running commands are gone. The next call opens a new session: "
    "bind and subscribe again."
)


class AgentError(Exception):
    """A failure the agent can act on. The message is what the agent reads."""


class Client(Protocol):
    """The part of RoISClient the session uses, so tests can stand in for it."""

    def on(self, name: Any, listener: Any) -> Any: ...

    async def disconnect(self) -> None: ...

    async def get_profile(self, condition: str = "") -> EngineProfile: ...

    async def get_error_detail(self, error_id: str, condition: str = "") -> list[Result]: ...

    async def bind(self, component_ref: str) -> None: ...

    async def release(self, component_ref: str) -> None: ...

    async def get_parameter(self, component_ref: str) -> list[Parameter]: ...

    async def set_parameter(
        self, component_ref: str, parameters: Sequence[Parameter | Mapping[str, Any]]
    ) -> str: ...

    async def execute(self, command_unit_list: Sequence[Any]) -> list[str]: ...

    async def get_command_result(self, command_id: str, condition: str = "") -> list[Result]: ...

    async def query(self, query_type: str, condition: str = "") -> list[Result]: ...

    async def subscribe(self, event_type: str, condition: str = "") -> str: ...

    async def unsubscribe(self, subscribe_id: str) -> None: ...


ClientFactory = Callable[[Settings], Awaitable[Client]]


async def connect_client(settings: Settings) -> Client:
    """Open a RoISClient on the gateway the settings name."""
    client: Client = await RoISClient.connect(
        settings.gateway_url,
        request_timeout=settings.request_timeout,
        connect_timeout=min(settings.request_timeout, 10.0),
    )
    return client


def code_name(code: ReturnCode | str) -> str:
    """A return code by name, such as OUT_OF_RESOURCES."""
    return code.name if isinstance(code, ReturnCode) else str(code)


def refusal(step: str, ref: str, code: str, hint: str | None = None) -> AgentError:
    """A structured failure: which step, which component, which code, and what to do."""
    return AgentError(
        json.dumps(
            {
                "step": step,
                "component_ref": ref,
                "return_code": code,
                "hint": hint or HINTS.get(code, ""),
            }
        )
    )


def error_hint(method: str, *, held: bool = False) -> str:
    """What an ERROR means for one method.

    ERROR is the engine's catch-all code. A query or a subscribe answers it when the
    component cannot serve, a command operation when the session holds no bind.
    """
    if method in ("rois.query.query", "rois.event.subscribe"):
        return NOT_OPERABLE
    if method in COMMAND_METHODS:
        return BIND_DROPPED if held else NEEDS_BIND
    return HINTS["ERROR"]


def rois_failure(
    error: RoISError, *, ref: str = "", held: bool = False, hint: str | None = None
) -> AgentError:
    """A RoISError written for the agent, naming the method, the code and a hint.

    Args:
        error: The failure.
        ref: The component the call was about.
        held: Whether this session had bound the component, which tells the hint of an
            ERROR from a command operation.
        hint: A hint that replaces the one of the return code.
    """
    code = code_name(error.return_code)
    text = f"{error.method} returned {code}"
    if ref:
        text += f" for {ref}"
    if hint is None:
        hint = error_hint(error.method, held=held) if code == "ERROR" else HINTS.get(code)
    return AgentError(f"{text}: {hint}" if hint else text)


def refused_value_hint(profile: HRIComponentProfile) -> str:
    """The hint of a value the component refused, naming the queries that list valid ones."""
    listing = [
        query.name
        for query in profile.query_profiles
        if query.name.startswith(("available_", "synthesizable_"))
    ]
    hint = "the component refused a name or value"
    if listing:
        return f"{hint}. The queries {', '.join(listing)} list the values it takes: call query"
    return f"{hint}, see describe_component for the types"


def failed_set_hint(profile: HRIComponentProfile) -> str:
    """The hint of a set_parameter command that ended ERROR.

    Inside a sequence, and in its completion, the engine reports a value the component
    refused as ERROR rather than BAD_PARAMETER, so the hint names the queries that list
    valid values instead of telling the agent not to retry.
    """
    return f"the component did not take the values: {refused_value_hint(profile)}"


@dataclass
class _Command:
    """A command this session started, until the agent stops asking about it."""

    ref: str
    command_type: str
    done: asyncio.Event = field(default_factory=asyncio.Event)
    status: str = RUNNING
    #: The event cursor before the command started, to find the errors that followed it.
    since: int = 0


class Session:
    """The RoIS session of one server process, and the work of every tool."""

    def __init__(self, settings: Settings, factory: ClientFactory = connect_client) -> None:
        self.settings = settings
        self.allow = AllowFilter(settings.allow)
        self.events = EventBuffer(settings.event_buffer)
        self._factory = factory
        self._client: Client | None = None
        self._open = False
        self._was_open = False
        self._connecting = asyncio.Lock()
        self._binds: dict[str, float] = {}
        # One lock per component, so a bind, a release and the temporary bind of
        # get_parameters on the same component never interleave.
        self._locks: dict[str, asyncio.Lock] = {}
        self._subscriptions: dict[str, tuple[str, str]] = {}
        self._commands: dict[str, _Command] = {}
        # The components this session ran start on, without a stop after it, which
        # shutdown stops.
        self._started: set[str] = set()
        # Completions that arrive before the reply naming their command, since a command
        # that ends at once can complete before execute returns.
        self._early: dict[str, str] = {}
        self._profiles: dict[str, HRIComponentProfile] | None = None
        self._idle_task: asyncio.Task[None] | None = None
        # Checks of the binds and subscriptions after a profile change, one at a time.
        self._checking = asyncio.Lock()
        self._checks: set[asyncio.Task[None]] = set()
        # Where the next wait_for_event without since starts: the cursor of the last
        # subscribe, run_commands or set_parameters, until a wait uses it. None: the next
        # wait starts at the newest entry, so it waits for a fresh one.
        self._cursor: int | None = None
        # What the agent must hear, until a tool response carries it.
        self._notices: list[str] = []

    # -----------------------------------------------------------------------
    # Connection
    # -----------------------------------------------------------------------

    async def client(self) -> Client:
        """The open client, connecting first if needed.

        A connection that was lost leaves a notice for the agent, which the next tool
        response carries, since its binds and subscriptions went with it.
        """
        async with self._connecting:
            if self._client is not None and self._open:
                return self._client
            if self._was_open:
                self._forget_session()
            try:
                client = await self._factory(self.settings)
            except (TransportError, OSError) as exc:
                raise AgentError(
                    f"Cannot reach the gateway at {self.settings.gateway_url}: {exc}"
                ) from exc
            client.on("rois.command.completed", self._on_completed)
            client.on("rois.event.notify_event", self._on_event)
            client.on("rois.system.notify_error", self._on_error)
            client.on("rois.system.profile_changed", self._on_profile_changed)
            client.on("close", self._on_close)
            self._client = client
            self._open = True
            self._was_open = True
            if self.settings.idle_release and self._idle_task is None:
                self._idle_task = asyncio.create_task(self._release_idle())
            return client

    def _forget_session(self) -> None:
        self._binds.clear()
        self._subscriptions.clear()
        self._started.clear()
        for command in self._commands.values():
            command.done.set()
        self._commands.clear()
        self._early.clear()
        self._profiles = None

    def take_notice(self) -> str | None:
        """The notices the agent has not heard yet, which the caller now delivers."""
        if not self._notices:
            return None
        notice = " ".join(dict.fromkeys(self._notices))
        self._notices.clear()
        return notice

    async def shutdown(self) -> None:
        """Stop what this session started, then release, unsubscribe and disconnect.

        Each step is best effort within SHUTDOWN_TIMEOUT, so a gateway that does not answer
        never holds up the exit. The disconnect ends what is left: the engine drops the
        binds and subscriptions of a session that goes, and aborts its running commands.
        """
        if self._idle_task is not None:
            self._idle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._idle_task
            self._idle_task = None
        for task in list(self._checks):
            task.cancel()
        client = self._client
        if client is None or not self._open:
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + SHUTDOWN_TIMEOUT

        async def bounded(call: Awaitable[object], what: str) -> None:
            remaining = deadline - loop.time()
            if remaining <= 0:
                if isinstance(call, Coroutine):
                    call.close()
                logger.warning("No time left at shutdown to %s", what)
                return
            try:
                await asyncio.wait_for(call, remaining)
            except (AgentError, RoISError, TransportError, TimeoutError) as exc:
                logger.warning("Could not %s at shutdown: %s", what, exc)

        started = sorted(ref for ref in self._started if ref in self._binds)
        if started:
            await bounded(self._stop_started(client, started), f"stop {', '.join(started)}")
        for subscribe_id in list(self._subscriptions):
            await bounded(client.unsubscribe(subscribe_id), f"unsubscribe {subscribe_id}")
        for ref in list(self._binds):
            await bounded(client.release(ref), f"release {ref}")
        self._binds.clear()
        self._subscriptions.clear()
        self._started.clear()
        # The close that the disconnect causes is not a lost connection.
        self._open = False
        self._was_open = False
        try:
            await asyncio.wait_for(client.disconnect(), 5.0)
        except (TransportError, TimeoutError) as exc:
            logger.warning("Could not disconnect cleanly: %s", exc)

    async def _stop_started(self, client: Client, refs: Sequence[str]) -> None:
        """Run stop on the components this session started that declare it, side by side.

        A sensor such as PersonDetection keeps working after its start completes, and a
        release does not stop it, so the session that started it stops it.
        """
        known = await self._component_profiles(client)
        stoppable = [
            ref
            for ref in refs
            if ref in known and any(c.name == "stop" for c in known[ref].command_profiles)
        ]
        if not stoppable:
            return
        branches = [
            {"command_list": [{"component_ref": ref, "command_type": "stop"}]} for ref in stoppable
        ]
        ids = await client.execute([{"branch_list": branches}])
        for command_id, ref in zip(ids, stoppable, strict=False):
            self._track(command_id, ref, "stop")
        await self._wait(ids, SHUTDOWN_TIMEOUT)

    # -----------------------------------------------------------------------
    # Notifications
    # -----------------------------------------------------------------------

    def _on_completed(self, params: CompletedParams) -> None:
        command = self._commands.get(params.command_id)
        data: dict[str, Any] = {"command_id": params.command_id, "status": params.status.value}
        if command is not None:
            command.status = params.status.value
            command.done.set()
            data["component_ref"] = command.ref
            data["command_type"] = command.command_type
        else:
            self._early[params.command_id] = params.status.value
        self.events.append("completed", data)

    def _on_event(self, params: NotifyEventParams) -> None:
        ref, _ = self._subscriptions.get(params.subscribe_id, ("", ""))
        self.events.append(
            "event",
            {
                "event_type": params.event_type,
                "component_ref": ref,
                "subscribe_id": params.subscribe_id,
                "event_id": params.event_id,
                "expire": params.expire,
                "results": values.decode(params.results),
            },
        )

    def _on_error(self, params: NotifyErrorParams) -> None:
        self.events.append(
            "error",
            {
                "error_id": params.error_id,
                "error_type": params.error_type.value,
                **params.model_dump(mode="json", exclude={"error_id", "error_type"}),
            },
        )

    def _on_profile_changed(self, _params: ProfileChangedParams) -> None:
        self._profiles = None
        self.events.append(
            "profile_changed", {"hint": "components joined or left, call list_components"}
        )
        # An engine that leaves the gateway takes this session's binds and subscriptions on
        # its components with it, also when it reconnects at once, so they are checked.
        if self._binds or self._subscriptions:
            task = asyncio.create_task(self._check_held())
            self._checks.add(task)
            task.add_done_callback(self._checks.discard)

    def _on_close(self, code: int, reason: str) -> None:
        if not self._open:
            return
        self._open = False
        # The engine ends a session that goes, with its binds, subscriptions and commands,
        # so every wait on a command ends now rather than at its timeout.
        for command in self._commands.values():
            if not command.done.is_set():
                command.status = CONNECTION_LOST
                command.done.set()
        self._binds.clear()
        self._subscriptions.clear()
        self._started.clear()
        self._profiles = None
        self.events.append(
            "connection_closed",
            {
                "code": code,
                "reason": reason,
                "hint": "the next tool call reconnects, then bind and subscribe again",
            },
        )
        self._notices.append(CONNECTION_LOST_NOTICE)

    async def _check_held(self) -> None:
        """Drop the binds and subscriptions the engine no longer holds, and say so.

        A bind is still held when get_parameter on its component answers, which needs one.
        A subscription is gone with its component, or with a bind lost on the same engine,
        since the engine drops both when the engine of the component leaves.
        """
        async with self._checking:
            client = self._client
            if client is None or not self._open:
                return
            try:
                engine = await client.get_profile("")
                current = dict(engine.component_profiles)
                self._profiles = current
                lost_binds: list[str] = []
                for ref in list(self._binds):
                    async with self._lock(ref):
                        if ref not in self._binds:
                            continue
                        if ref in current and await self._still_held(client, ref):
                            continue
                        self._drop_bind(ref)
                        lost_binds.append(ref)
            except (RoISError, TransportError) as exc:
                logger.warning("Could not check the binds after a profile change: %s", exc)
                return
            lost_engines = {profiles.engine_of(ref) for ref in lost_binds}
            lost_subscriptions = [
                {"subscribe_id": sid, "component_ref": ref, "event_type": event_type}
                for sid, (ref, event_type) in list(self._subscriptions.items())
                if ref not in current or profiles.engine_of(ref) in lost_engines
            ]
            for entry in lost_subscriptions:
                self._subscriptions.pop(entry["subscribe_id"], None)
            if not lost_binds and not lost_subscriptions:
                return
            hint = (
                "the engine of these components left or reconnected to the gateway, which "
                "dropped this session's binds and subscriptions on them. Bind and subscribe "
                "again once list_components shows them"
            )
            self.events.append(
                "lost",
                {"binds": lost_binds, "subscriptions": lost_subscriptions, "hint": hint},
            )
            names = lost_binds + [
                f"subscription {e['subscribe_id']} ({e['component_ref']} {e['event_type']})"
                for e in lost_subscriptions
            ]
            self._notices.append(f"Lost: {', '.join(names)}. {hint[0].upper()}{hint[1:]}.")

    async def _still_held(self, client: Client, ref: str) -> bool:
        """Whether the engine still holds this session's bind on a component."""
        try:
            await client.get_parameter(ref)
        except RoISError as error:
            return code_name(error.return_code) not in ("ERROR", "UNSUPPORTED")
        return True

    # -----------------------------------------------------------------------
    # Profiles
    # -----------------------------------------------------------------------

    async def _component_profiles(self, client: Client) -> dict[str, HRIComponentProfile]:
        if self._profiles is None:
            engine = await self._call(client.get_profile(""))
            self._profiles = dict(engine.component_profiles)
        return self._profiles

    async def profile_of(self, ref: str) -> HRIComponentProfile:
        """The profile of one component.

        Raises:
            AgentError: The engine lists no such component.
        """
        client = await self.client()
        found = (await self._component_profiles(client)).get(ref)
        if found is None:
            self._profiles = None
            found = (await self._component_profiles(client)).get(ref)
        if found is None:
            raise AgentError(f"No component {ref!r}. Call list_components for the refs.")
        return found

    # -----------------------------------------------------------------------
    # Discover
    # -----------------------------------------------------------------------

    async def list_components(self, pattern: str = "") -> dict[str, Any]:
        """Every component, or those whose ref matches a LIKE pattern, with its status."""
        client = await self.client()
        condition = like(COMPONENT_REF, pattern) if pattern else ""
        engine = await self._call(client.get_profile(condition))
        if not pattern:
            self._profiles = dict(engine.component_profiles)
        components = []
        for ref, profile in sorted(engine.component_profiles.items()):
            entry = profiles.summary(ref, profile)
            entry["component_status"] = await self._declared_status(client, ref, profile)
            entry["held_by_this_session"] = ref in self._binds
            entry["actions_allowed"] = self.settings.allow_actions and self.allow.allows(ref)
            components.append(entry)
        return self._with_notice({"components": components})

    async def _declared_status(
        self, client: Client, ref: str, profile: HRIComponentProfile
    ) -> str | None:
        # A component whose profile has no component_status query, such as
        # SystemInformation, reports no status, so it is not asked.
        if not any(q.name == "component_status" for q in profile.query_profiles):
            return None
        return await self._status(client, ref)

    async def _status(self, client: Client, ref: str) -> str | None:
        """The component_status this session sees: BUSY when another session holds it."""
        try:
            results = await client.query("component_status", component_ref(ref))
        except (RoISError, TransportError):
            return None
        for result in values.decode(results):
            if result["name"] == "status":
                return str(result["value"])
        decoded = values.decode(results)
        return str(decoded[0]["value"]) if decoded else None

    async def describe_component(self, ref: str) -> dict[str, Any]:
        """The condensed profile of a component, with current parameter values if bound."""
        client = await self.client()
        profile = await self.profile_of(ref)
        described = profiles.describe(ref, profile)
        described["component_status"] = await self._status(client, ref)
        described["held_by_this_session"] = ref in self._binds
        if ref in self._binds and profile.parameter_profiles:
            with contextlib.suppress(RoISError, TransportError):
                current = {
                    item["name"]: item["value"]
                    for item in values.decode(await client.get_parameter(ref))
                }
                for parameter in described["parameters"]:
                    if parameter["name"] in current:
                        parameter["value"] = current[parameter["name"]]
        return self._with_notice(described)

    async def query(self, ref: str, query_type: str) -> dict[str, Any]:
        """Run a query on one component."""
        client = await self.client()
        results = await self._call(client.query(query_type, component_ref(ref)), ref=ref)
        self._touch(ref)
        return self._with_notice(
            {"component_ref": ref, "query_type": query_type, "results": values.decode(results)}
        )

    async def get_parameters(self, ref: str) -> dict[str, Any]:
        """The current parameters of a component.

        RoIS reads parameters through the command interface, which needs a bind. A
        component this session holds is read directly. A component that takes a bind per
        session, such as a sensor, is bound for the read and released after, which takes it
        from nobody, but only by a server that may act on it. An actuation component must
        be bound first.
        """
        client = await self.client()
        async with self._lock(ref):
            if ref in self._binds:
                parameters = await self._call(client.get_parameter(ref), ref=ref)
                self._touch(ref)
                return self._with_notice(
                    {"component_ref": ref, "parameters": values.decode(parameters)}
                )
            profile = await self.profile_of(ref)
            if profile.function is ComponentFunction.ACTUATION:
                raise AgentError(
                    f"Reading the parameters of {ref} needs a bind by this session, and it is "
                    "an actuation component that one session holds at a time. Call bind first."
                )
            if not self.settings.allow_actions or not self.allow.allows(ref):
                why = (
                    "this server is read-only"
                    if not self.settings.allow_actions
                    else f"this server acts only on components matching {self.allow.describe()}"
                )
                raise AgentError(
                    f"Reading the parameters of {ref} needs a bind by this session, and {why}, "
                    "so it does not bind it. describe_component shows the parameters and the "
                    "value each has before anyone sets it."
                )
            await self._call(client.bind(ref), ref=ref)
            try:
                parameters = await self._call(client.get_parameter(ref), ref=ref)
            finally:
                with contextlib.suppress(RoISError, TransportError):
                    await client.release(ref)
        return self._with_notice({"component_ref": ref, "parameters": values.decode(parameters)})

    # -----------------------------------------------------------------------
    # Act
    # -----------------------------------------------------------------------

    def _check_allowed(self, ref: str) -> None:
        if not self.allow.allows(ref):
            raise refusal(
                "allow",
                ref,
                "NOT_ALLOWED",
                f"this server allows actions only on components matching {self.allow.describe()}",
            )

    async def bind(self, ref: str, wait_seconds: float = 0) -> dict[str, Any]:
        """Reserve a component, retrying while another session holds it if asked to.

        The bind always goes to the engine, which answers OK to a session that holds it
        already, so a bind the engine dropped is taken again rather than assumed.
        """
        self._check_allowed(ref)
        client = await self.client()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, min(wait_seconds, self.settings.command_timeout))
        async with self._lock(ref):
            while True:
                try:
                    await client.bind(ref)
                    break
                except RoISError as error:
                    code = code_name(error.return_code)
                    if code == "OUT_OF_RESOURCES" and loop.time() + BIND_RETRY_INTERVAL < deadline:
                        await asyncio.sleep(BIND_RETRY_INTERVAL)
                        continue
                    # A bind this session had recorded is not held, or it would be OK.
                    self._drop_bind(ref)
                    raise refusal("bind", ref, code) from error
            self._binds[ref] = loop.time()
        return self._with_notice({"component_ref": ref, "bound": True})

    async def release(self, ref: str) -> dict[str, Any]:
        """Release a component, and report the commands the engine aborted with it.

        The engine aborts the commands of this session that run on the component. A command
        still waiting its turn in a sequence may run all the same, so only the commands
        that end with ABORT soon after the release are reported as aborted.
        """
        client = await self.client()
        async with self._lock(ref):
            running = [
                cid
                for cid, cmd in self._commands.items()
                if cmd.ref == ref and not cmd.done.is_set()
            ]
            try:
                await client.release(ref)
            except RoISError as error:
                if code_name(error.return_code) == "UNSUPPORTED":
                    # The engine lists no such component now, so this session holds nothing.
                    self._drop_bind(ref)
                raise rois_failure(error, ref=ref) from error
            self._drop_bind(ref)
        await self._wait(running, RELEASE_SETTLE)
        result: dict[str, Any] = {"component_ref": ref, "released": True}
        ended = {cid: self._commands[cid] for cid in running if cid in self._commands}
        aborted = [cid for cid, cmd in ended.items() if cmd.status == "ABORT"]
        still = [cid for cid, cmd in ended.items() if not cmd.done.is_set()]
        if aborted:
            result["aborted_command_ids"] = aborted
        if still:
            result["still_running_command_ids"] = still
            result["hint"] = (
                "the engine did not end these with the release, so they may still run: "
                "follow them with command_status or get_events"
            )
        return self._with_notice(result)

    async def set_parameters(
        self, ref: str, new_values: Mapping[str, object], wait: bool = True
    ) -> dict[str, Any]:
        """Set parameters from plain JSON values, typed by the profile."""
        self._check_allowed(ref)
        client = await self.client()
        if ref not in self._binds:
            raise refusal("bind", ref, "NOT_BOUND")
        profile = await self.profile_of(ref)
        try:
            items = values.encode(new_values, profile.parameter_profiles, refuse_read_only=True)
        except values.ValueRefusedError as exc:
            raise AgentError(f"BAD_PARAMETER: parameter {exc}") from exc
        cursor = self._hand_out(self.events.last)
        command_id = await self._call(
            client.set_parameter(ref, items), ref=ref, hint=refused_value_hint(profile)
        )
        self._touch(ref)
        command = self._track(command_id, ref, "set_parameter", since=cursor)
        result: dict[str, Any] = {"component_ref": ref, "command_id": command_id, "cursor": cursor}
        if wait:
            await self._wait([command_id], self.settings.command_timeout)
            result["status"] = command.status
            if command.status == "ERROR":
                result["hint"] = failed_set_hint(profile)
            elif command.status in STATUS_HINTS:
                result["hint"] = STATUS_HINTS[command.status]
        return self._with_notice(result)

    async def run_commands(
        self,
        steps: Sequence[Mapping[str, Any]],
        wait: bool = True,
        timeout: float | None = None,
        auto_bind: bool = AUTO_BIND_DEFAULT,
    ) -> dict[str, Any]:
        """Run a sequence of commands and parallel groups.

        With auto_bind, every component the steps name is bound first, all or nothing: if a
        bind fails, the binds this call made are released and nothing runs. The bind goes
        to the engine also for a component this session holds, which renews a bind the
        engine dropped.
        """
        client = await self.client()
        items, order = await self._parse_steps(steps)
        refs = list(dict.fromkeys(ref for ref, _ in order))
        for ref in refs:
            self._check_allowed(ref)
        if not auto_bind:
            for ref in refs:
                if ref not in self._binds:
                    raise refusal("bind", ref, "NOT_BOUND")
        made: list[str] = []
        failed: AgentError | None = None
        for ref in refs if auto_bind else ():
            async with self._lock(ref):
                held = ref in self._binds
                try:
                    await client.bind(ref)
                except RoISError as error:
                    self._drop_bind(ref)
                    failed = refusal("bind", ref, code_name(error.return_code))
                    break
                if not held:
                    made.append(ref)
                self._binds[ref] = asyncio.get_running_loop().time()
        if failed is not None:
            await self._release_quietly(client, made)
            raise failed
        cursor = self._hand_out(self.events.last)
        try:
            ids = await client.execute(items)
        except RoISError as error:
            lost: list[str] = []
            if code_name(error.return_code) == "ERROR":
                lost = await self._lost_binds(client, [ref for ref in refs if ref not in made])
            await self._release_quietly(client, made)
            if lost:
                hint = f"{BIND_DROPPED}. Not held any more: {', '.join(lost)}"
                raise rois_failure(error, hint=hint) from error
            raise rois_failure(error) from error
        except TransportError:
            await self._release_quietly(client, made)
            raise
        for command_id, (ref, command_type) in zip(ids, order, strict=False):
            self._track(command_id, ref, command_type, since=cursor)
            if command_type == "start":
                self._started.add(ref)
            elif command_type == "stop":
                self._started.discard(ref)
        for ref in refs:
            self._touch(ref)
        result: dict[str, Any] = {"command_ids": ids, "cursor": cursor}
        if made:
            result["bound_by_this_call"] = made
        if wait:
            limit = min(timeout or self.settings.command_timeout, self.settings.command_timeout)
            await self._wait(ids, limit)
            result["commands"] = await self._statuses(client, ids)
        return self._with_notice(result)

    async def _lost_binds(self, client: Client, refs: Sequence[str]) -> list[str]:
        """The components of refs whose bind the engine dropped, now forgotten here too."""
        lost = []
        for ref in refs:
            try:
                held = await self._still_held(client, ref)
            except TransportError:
                continue
            if not held:
                self._drop_bind(ref)
                lost.append(ref)
        return lost

    async def command_status(self, command_ids: Sequence[str]) -> dict[str, Any]:
        """The status of commands this session ran, with their results once they ended."""
        client = await self.client()
        return self._with_notice({"commands": await self._statuses(client, command_ids)})

    async def _statuses(self, client: Client, command_ids: Sequence[str]) -> list[dict[str, Any]]:
        statuses: list[dict[str, Any]] = []
        failed: dict[str, str] | None = None
        for command_id in command_ids:
            command = self._commands.get(command_id)
            entry: dict[str, Any] = {"command_id": command_id}
            statuses.append(entry)
            if command is None:
                entry["status"] = "UNKNOWN"
                entry["hint"] = "not started by this session, or from a session that was lost"
                continue
            entry.update(
                component_ref=command.ref,
                command_type=command.command_type,
                status=command.status,
            )
            if not command.done.is_set():
                continue
            if command.status == "OK":
                with contextlib.suppress(RoISError, TransportError):
                    results = await client.get_command_result(command_id)
                    if results:
                        entry["results"] = values.decode(results)
                continue
            if command.status in STATUS_HINTS:
                entry["hint"] = STATUS_HINTS[command.status]
            if command.status == "ABORT" and failed is not None:
                entry["hint"] = (
                    f"the command did not run to its end because {failed['command_id']} on "
                    f"{failed['component_ref']} ended {failed['status']} before it, and a "
                    "failed command ends the rest of its sequence"
                )
            elif command.status in ("ERROR", "TIMEOUT", "OUT_OF_RESOURCES"):
                failed = {
                    "command_id": command_id,
                    "component_ref": command.ref,
                    "status": command.status,
                }
                if command.status == "ERROR":
                    await self._explain_error(client, command, entry)
        return statuses

    async def _explain_error(
        self, client: Client, command: _Command, entry: dict[str, Any]
    ) -> None:
        """Add what the engine reported about a command that ended ERROR."""
        profile = None
        with contextlib.suppress(AgentError, TransportError):
            profile = (await self._component_profiles(client)).get(command.ref)
        if profile is not None:
            if command.command_type == "set_parameter":
                entry["hint"] = failed_set_hint(profile)
            status = await self._declared_status(client, command.ref, profile)
            if status is not None:
                entry["component_status"] = status
        engine = profiles.engine_of(command.ref)
        found, _, _ = self.events.since(command.since, self.settings.event_buffer)
        errors = [
            e.as_dict()
            for e in found
            if e.kind == "error" and profiles.engine_of(str(e.data.get("error_id", ""))) == engine
        ]
        if errors:
            entry["errors"] = errors

    async def _parse_steps(
        self, steps: Sequence[Mapping[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
        """Turn the agent's steps into execute items, typing every argument by the profile.

        Returns:
            The items, and the ref and command_type of every command in the order execute
            returns their ids.
        """
        if not steps:
            raise AgentError("steps is empty: give at least one command")
        items: list[dict[str, Any]] = []
        order: list[tuple[str, str]] = []
        for index, step in enumerate(steps):
            if "branch_list" in step:
                branches = []
                for branch in step["branch_list"]:
                    commands = (
                        branch.get("command_list", []) if isinstance(branch, Mapping) else branch
                    )
                    if not commands:
                        raise AgentError(f"step {index}: a branch needs at least one command")
                    units = [await self._unit(command, order, index) for command in commands]
                    branches.append({"command_list": units})
                group: dict[str, Any] = {"branch_list": branches}
                if step.get("delay_time") is not None:
                    group["delay_time"] = int(step["delay_time"])
                items.append(group)
            else:
                items.append(await self._unit(step, order, index))
        return items, order

    async def _unit(
        self, command: Mapping[str, Any], order: list[tuple[str, str]], index: int
    ) -> dict[str, Any]:
        ref = command.get("component_ref")
        command_type = command.get("command_type")
        if not isinstance(ref, str) or not isinstance(command_type, str):
            raise AgentError(
                f"step {index}: a command needs component_ref and command_type strings"
            )
        profile = await self.profile_of(ref)
        declared = {profile_.name: profile_ for profile_ in profile.command_profiles}
        parameters = {parameter.name for parameter in profile.parameter_profiles}
        arguments = command.get("arguments") or {}
        if not isinstance(arguments, Mapping):
            raise AgentError(f"step {index}: arguments must be an object of name to value")
        unit: dict[str, Any] = {"component_ref": ref, "command_type": command_type}
        if command_type == "set_parameter" and command_type not in declared:
            # RoIS runs set_parameter as a command of a sequence too, so parameters can be
            # set right before the command that reads them, in the same call.
            if not parameters:
                raise AgentError(f"BAD_PARAMETER: {ref} has no parameters to set")
            if not arguments:
                raise AgentError(
                    f"step {index}: set_parameter needs arguments, parameter name to value"
                )
            try:
                unit["arguments"] = values.encode(
                    arguments, profile.parameter_profiles, refuse_read_only=True
                )
            except values.ValueRefusedError as exc:
                raise AgentError(f"BAD_PARAMETER: {ref} parameter {exc}") from exc
            order.append((ref, command_type))
            return unit
        if command_type not in declared:
            commands = sorted(declared) + (["set_parameter"] if parameters else [])
            raise AgentError(
                f"BAD_PARAMETER: {ref} has no command {command_type!r} "
                f"(commands: {', '.join(commands) or 'none'})"
            )
        if arguments:
            try:
                unit["arguments"] = values.encode(arguments, declared[command_type].arguments)
            except values.ValueRefusedError as exc:
                text = f"BAD_PARAMETER: {ref} {command_type} argument {exc}"
                if exc.name in parameters:
                    text += (
                        f". {exc.name} is a parameter of {ref}, not an argument of "
                        f'{command_type}: put a step {{"component_ref": "{ref}", '
                        f'"command_type": "set_parameter", "arguments": '
                        f'{{"{exc.name}": ...}}}} before it, or call set_parameters first'
                    )
                raise AgentError(text) from exc
        order.append((ref, command_type))
        return unit

    async def _wait(self, command_ids: Sequence[str], timeout: float) -> None:
        events = [self._commands[cid].done for cid in command_ids if cid in self._commands]
        if not events:
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.gather(*(event.wait() for event in events)), timeout)

    async def _release_quietly(self, client: Client, refs: Sequence[str]) -> None:
        for ref in refs:
            async with self._lock(ref):
                with contextlib.suppress(RoISError, TransportError):
                    await client.release(ref)
                self._drop_bind(ref)

    def _track(self, command_id: str, ref: str, command_type: str, since: int = 0) -> _Command:
        """Follow a command this session started, taking a completion that came first."""
        command = self._commands.setdefault(command_id, _Command(ref, command_type, since=since))
        status = self._early.pop(command_id, None)
        if status is not None:
            command.status = status
            command.done.set()
        return command

    def _lock(self, ref: str) -> asyncio.Lock:
        return self._locks.setdefault(ref, asyncio.Lock())

    def _drop_bind(self, ref: str) -> None:
        """Forget a bind, and the start that shutdown would stop, which needs the bind."""
        self._binds.pop(ref, None)
        self._started.discard(ref)

    def _touch(self, ref: str) -> None:
        """Mark a held component as used now, for the idle release."""
        if ref in self._binds:
            self._binds[ref] = asyncio.get_running_loop().time()

    async def _release_idle(self) -> None:
        """Release binds idle longer than the setting, and tell the agent through get_events."""
        idle = self.settings.idle_release or 0
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(min(max(idle / 4, 0.05), 5.0))
            client = self._client
            if client is None or not self._open:
                continue
            now = loop.time()
            for ref, last in list(self._binds.items()):
                if now - last < idle:
                    continue
                with contextlib.suppress(RoISError, TransportError):
                    await client.release(ref)
                self._drop_bind(ref)
                self.events.append(
                    "idle_release",
                    {
                        "component_ref": ref,
                        "idle_seconds": idle,
                        "hint": "released after no call on it, bind again to use it",
                    },
                )

    # -----------------------------------------------------------------------
    # Observe
    # -----------------------------------------------------------------------

    async def subscribe(self, ref: str, event_type: str) -> dict[str, Any]:
        """Subscribe to an event of one component. Its occurrences go to get_events."""
        client = await self.client()
        # The cursor comes first, so an occurrence that arrives with the reply is after it.
        cursor = self.events.last
        subscribe_id = await self._call(client.subscribe(event_type, component_ref(ref)), ref=ref)
        self._subscriptions[subscribe_id] = (ref, event_type)
        result: dict[str, Any] = {
            "subscribe_id": subscribe_id,
            "component_ref": ref,
            "event_type": event_type,
            "cursor": self._hand_out(cursor),
        }
        hint = await self._start_hint(ref)
        if hint:
            result["hint"] = hint
        return self._with_notice(result)

    async def _start_hint(self, ref: str) -> str | None:
        """For a component with a start command, that it may send events only once started.

        A sensor such as PersonDetection often reports only between its start and stop
        commands, which a subscribe does not run.
        """
        if ref in self._started:
            return None
        with contextlib.suppress(AgentError, RoISError, TransportError):
            profile = await self.profile_of(ref)
            if not any(command.name == "start" for command in profile.command_profiles):
                return None
            text = "This component may send events only between its start and stop commands."
            if self.settings.allow_actions and self.allow.allows(ref):
                return (
                    f"{text} If none arrive, bind it and run_commands start on it, and stop it "
                    "when done."
                )
            return (
                f"{text} This server cannot run commands on it (read-only, or outside its "
                "--allow patterns). If none arrive, tell the user that another client has to "
                "start it, or that the server needs --allow-actions."
            )
        return None

    async def unsubscribe(self, subscribe_id: str) -> dict[str, Any]:
        """Cancel a subscription."""
        client = await self.client()
        await self._call(client.unsubscribe(subscribe_id))
        self._subscriptions.pop(subscribe_id, None)
        return self._with_notice({"subscribe_id": subscribe_id, "unsubscribed": True})

    def get_events(self, since: int = 0, limit: int = 50) -> dict[str, Any]:
        """The buffered notifications after a cursor."""
        entries, cursor, dropped = self.events.since(since, limit)
        if self._cursor is not None:
            # A wait after a command starts after what the agent has read since, but never
            # goes back, as when it reads from the oldest entry kept.
            self._cursor = max(self._cursor, cursor)
        result: dict[str, Any] = {
            "entries": [entry.as_dict() for entry in entries],
            "cursor": cursor,
            "more": self.events.last > cursor,
        }
        if dropped:
            result["dropped"] = dropped
        return self._with_notice(result)

    async def wait_for_event(
        self,
        event_type: str = "",
        ref: str = "",
        timeout: float = 30.0,
        since: int | None = None,
    ) -> dict[str, Any]:
        """Wait for an event that matches, an error, a loss, or the timeout.

        Without ``since``, the first wait after subscribe, run_commands or set_parameters
        starts at the cursor that call returned, so an event that a component sends while
        a command runs, before its completion, still counts. Any other wait starts at the
        newest entry, so it waits for a fresh event rather than returning an old one.
        """
        if since is not None:
            start = since
        elif self._cursor is not None:
            start = self._cursor
        else:
            start = self.events.last
        # A wait uses the cursor of the call before it once.
        self._cursor = None

        def matches(entry: Entry) -> bool:
            if entry.kind in ("error", "connection_closed", "lost"):
                return True
            if entry.kind != "event":
                return False
            if event_type and entry.data.get("event_type") != event_type:
                return False
            return not ref or entry.data.get("component_ref") == ref

        limit = max(0.0, min(timeout, self.settings.command_timeout))
        found = await self.events.wait_for(start, matches, limit)
        if found is None:
            # The cursor is where the wait started, so a wait with another filter can pass
            # it as since and not skip an entry.
            return self._with_notice({"timed_out": True, "cursor": start})
        return self._with_notice(
            {"timed_out": False, "entry": found.as_dict(), "cursor": found.seq}
        )

    async def get_error_detail(self, error_id: str) -> dict[str, Any]:
        """The details of an error from a notify_error entry."""
        client = await self.client()
        results = await self._call(client.get_error_detail(error_id))
        return self._with_notice({"error_id": error_id, "results": values.decode(results)})

    def state(self) -> dict[str, Any]:
        """What this session holds: binds, subscriptions, running commands, connection."""
        return {
            "gateway_url": self.settings.gateway_url,
            "connected": self._open,
            "allow_actions": self.settings.allow_actions,
            "allow": list(self.allow.patterns),
            "binds": sorted(self._binds),
            "subscriptions": [
                {"subscribe_id": sid, "component_ref": ref, "event_type": event_type}
                for sid, (ref, event_type) in self._subscriptions.items()
            ],
            "running_commands": [
                {"command_id": cid, "component_ref": cmd.ref, "command_type": cmd.command_type}
                for cid, cmd in self._commands.items()
                if not cmd.done.is_set()
            ],
            "event_cursor": self.events.last,
        }

    # -----------------------------------------------------------------------
    # Private
    # -----------------------------------------------------------------------

    async def _call[T](self, call: Awaitable[T], *, ref: str = "", hint: str | None = None) -> T:
        """Await a RoIS call, turning a RoISError into a failure the agent can read.

        An ERROR from a command operation on a component this session had bound means the
        engine dropped the bind, so it is forgotten here too.

        Args:
            call: The RoIS call.
            ref: The component it is about.
            hint: The hint of a BAD_PARAMETER, in place of the general one.
        """
        try:
            return await call
        except RoISError as error:
            code = code_name(error.return_code)
            held = code == "ERROR" and error.method in COMMAND_METHODS and ref in self._binds
            if held:
                self._drop_bind(ref)
            override = hint if code == "BAD_PARAMETER" else None
            raise rois_failure(error, ref=ref, held=held, hint=override) from error

    def _hand_out(self, cursor: int) -> int:
        """Record the cursor of a call that starts something, where the next wait starts."""
        self._cursor = cursor
        return cursor

    def _with_notice(self, result: dict[str, Any]) -> dict[str, Any]:
        notice = self.take_notice()
        if notice:
            result["notice"] = notice
        return result
