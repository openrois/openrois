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
from collections.abc import Awaitable, Callable, Mapping, Sequence
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

#: What an agent can do about each return code.
HINTS: dict[str, str] = {
    "OUT_OF_RESOURCES": (
        "another session holds this component. Try later, call bind with wait_seconds, "
        "or pick another component"
    ),
    "BAD_PARAMETER": "a name or value does not match the profile, see describe_component",
    "UNSUPPORTED": "the component does not declare this, see describe_component",
    "ERROR": (
        "the engine refused the call. A command operation needs a bind by this session "
        "on the component"
    ),
    "TIMEOUT": "the component did not answer in time",
    "NOT_BOUND": "not bound by this session, call bind first",
    "NOT_ALLOWED": "this server was started with --allow patterns that exclude the component",
}

#: The status of a command still running when a wait ends.
RUNNING = "RUNNING"


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


def rois_failure(error: RoISError, *, ref: str = "") -> AgentError:
    """A RoISError written for the agent, naming the method, the code and a hint."""
    code = code_name(error.return_code)
    text = f"{error.method} returned {code}"
    if ref:
        text += f" for {ref}"
    hint = HINTS.get(code)
    return AgentError(f"{text}: {hint}" if hint else text)


@dataclass
class _Command:
    """A command this session started, until the agent stops asking about it."""

    ref: str
    command_type: str
    done: asyncio.Event = field(default_factory=asyncio.Event)
    status: str = RUNNING


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
        self._subscriptions: dict[str, tuple[str, str]] = {}
        self._commands: dict[str, _Command] = {}
        # Completions that arrive before the reply naming their command, since a command
        # that ends at once can complete before execute returns.
        self._early: dict[str, str] = {}
        self._profiles: dict[str, HRIComponentProfile] | None = None
        self._idle_task: asyncio.Task[None] | None = None

    # -----------------------------------------------------------------------
    # Connection
    # -----------------------------------------------------------------------

    async def client(self) -> tuple[Client, str | None]:
        """The open client, connecting first if needed.

        Returns:
            The client, and a notice for the agent when this call replaced a session that
            was lost, since its binds and subscriptions went with it.
        """
        async with self._connecting:
            if self._client is not None and self._open:
                return self._client, None
            notice = None
            if self._was_open:
                notice = (
                    "The connection to the gateway was lost and is open again as a new "
                    "session. The binds, subscriptions and running commands of the old "
                    "session are gone: bind and subscribe again."
                )
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
            return client, notice

    def _forget_session(self) -> None:
        self._binds.clear()
        self._subscriptions.clear()
        for command in self._commands.values():
            command.done.set()
        self._commands.clear()
        self._early.clear()
        self._profiles = None

    async def shutdown(self) -> None:
        """Release every bind, which aborts this session's running commands, and disconnect."""
        if self._idle_task is not None:
            self._idle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._idle_task
            self._idle_task = None
        client = self._client
        if client is None or not self._open:
            return
        for ref in list(self._binds):
            try:
                await asyncio.wait_for(client.release(ref), 5.0)
            except (RoISError, TransportError, TimeoutError) as exc:
                logger.warning("Could not release %s at shutdown: %s", ref, exc)
        self._binds.clear()
        try:
            await asyncio.wait_for(client.disconnect(), 5.0)
        except (TransportError, TimeoutError) as exc:
            logger.warning("Could not disconnect cleanly: %s", exc)
        self._open = False
        self._was_open = False

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

    def _on_close(self, code: int, reason: str) -> None:
        if not self._open:
            return
        self._open = False
        self.events.append(
            "connection_closed",
            {
                "code": code,
                "reason": reason,
                "hint": "the next tool call reconnects, then bind and subscribe again",
            },
        )

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
        client, _ = await self.client()
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
        client, notice = await self.client()
        condition = like(COMPONENT_REF, pattern) if pattern else ""
        engine = await self._call(client.get_profile(condition))
        if not pattern:
            self._profiles = dict(engine.component_profiles)
        components = []
        for ref, profile in sorted(engine.component_profiles.items()):
            entry = profiles.summary(ref, profile)
            # A component whose profile has no component_status query, such as
            # SystemInformation, reports no status, so it is not asked.
            declared = any(q.name == "component_status" for q in profile.query_profiles)
            entry["component_status"] = await self._status(client, ref) if declared else None
            entry["held_by_this_session"] = ref in self._binds
            entry["actions_allowed"] = self.settings.allow_actions and self.allow.allows(ref)
            components.append(entry)
        return self._with_notice({"components": components}, notice)

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
        client, notice = await self.client()
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
        return self._with_notice(described, notice)

    async def query(self, ref: str, query_type: str) -> dict[str, Any]:
        """Run a query on one component."""
        client, notice = await self.client()
        results = await self._call(client.query(query_type, component_ref(ref)), ref=ref)
        self._touch(ref)
        return self._with_notice(
            {"component_ref": ref, "query_type": query_type, "results": values.decode(results)},
            notice,
        )

    async def get_parameters(self, ref: str) -> dict[str, Any]:
        """The current parameters of a component.

        RoIS reads parameters through the command interface, which needs a bind. A
        component this session holds is read directly. A component that takes a bind per
        session, such as a sensor, is bound for the read and released after, which takes it
        from nobody. An actuation component must be bound first.
        """
        client, notice = await self.client()
        if ref in self._binds:
            parameters = await self._call(client.get_parameter(ref), ref=ref)
            self._touch(ref)
        else:
            profile = await self.profile_of(ref)
            if profile.function is ComponentFunction.ACTUATION:
                raise AgentError(
                    f"Reading the parameters of {ref} needs a bind by this session, and it is "
                    "an actuation component that one session holds at a time. Call bind first."
                )
            await self._call(client.bind(ref), ref=ref)
            try:
                parameters = await self._call(client.get_parameter(ref), ref=ref)
            finally:
                with contextlib.suppress(RoISError, TransportError):
                    await client.release(ref)
        return self._with_notice(
            {"component_ref": ref, "parameters": values.decode(parameters)}, notice
        )

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
        """Reserve a component, retrying while another session holds it if asked to."""
        self._check_allowed(ref)
        client, notice = await self.client()
        if ref in self._binds:
            return self._with_notice({"component_ref": ref, "bound": True, "already": True}, notice)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, min(wait_seconds, self.settings.command_timeout))
        while True:
            try:
                await client.bind(ref)
                break
            except RoISError as error:
                code = code_name(error.return_code)
                if code == "OUT_OF_RESOURCES" and loop.time() + BIND_RETRY_INTERVAL < deadline:
                    await asyncio.sleep(BIND_RETRY_INTERVAL)
                    continue
                raise refusal("bind", ref, code) from error
        self._binds[ref] = loop.time()
        return self._with_notice({"component_ref": ref, "bound": True}, notice)

    async def release(self, ref: str) -> dict[str, Any]:
        """Release a component. The engine aborts this session's commands still running on it."""
        client, notice = await self.client()
        running = [
            cid for cid, cmd in self._commands.items() if cmd.ref == ref and not cmd.done.is_set()
        ]
        await self._call(client.release(ref), ref=ref)
        self._binds.pop(ref, None)
        result: dict[str, Any] = {"component_ref": ref, "released": True}
        if running:
            result["aborted_command_ids"] = running
        return self._with_notice(result, notice)

    async def set_parameters(
        self, ref: str, new_values: Mapping[str, object], wait: bool = True
    ) -> dict[str, Any]:
        """Set parameters from plain JSON values, typed by the profile."""
        self._check_allowed(ref)
        client, notice = await self.client()
        if ref not in self._binds:
            raise refusal("bind", ref, "NOT_BOUND")
        profile = await self.profile_of(ref)
        try:
            items = values.encode(new_values, profile.parameter_profiles, refuse_read_only=True)
        except values.ValueRefusedError as exc:
            raise AgentError(f"BAD_PARAMETER: parameter {exc}") from exc
        command_id = await self._call(client.set_parameter(ref, items), ref=ref)
        self._touch(ref)
        command = self._track(command_id, ref, "set_parameter")
        result: dict[str, Any] = {"component_ref": ref, "command_id": command_id}
        if wait:
            await self._wait([command_id], self.settings.command_timeout)
            result["status"] = command.status
        return self._with_notice(result, notice)

    async def run_commands(
        self,
        steps: Sequence[Mapping[str, Any]],
        wait: bool = True,
        timeout: float | None = None,
        auto_bind: bool = AUTO_BIND_DEFAULT,
    ) -> dict[str, Any]:
        """Run a sequence of commands and parallel groups.

        With auto_bind, every component the steps name is bound first, all or nothing: if a
        bind fails, the binds this call made are released and nothing runs.
        """
        client, notice = await self.client()
        items, order = await self._parse_steps(steps)
        refs = list(dict.fromkeys(ref for ref, _ in order))
        for ref in refs:
            self._check_allowed(ref)
        made: list[str] = []
        for ref in refs:
            if ref in self._binds:
                continue
            if not auto_bind:
                raise refusal("bind", ref, "NOT_BOUND")
            try:
                await client.bind(ref)
            except RoISError as error:
                await self._release_quietly(client, made)
                raise refusal("bind", ref, code_name(error.return_code)) from error
            made.append(ref)
            self._binds[ref] = asyncio.get_running_loop().time()
        try:
            ids = await client.execute(items)
        except RoISError as error:
            await self._release_quietly(client, made)
            raise rois_failure(error) from error
        except TransportError:
            await self._release_quietly(client, made)
            raise
        for command_id, (ref, command_type) in zip(ids, order, strict=False):
            self._track(command_id, ref, command_type)
        for ref in refs:
            self._touch(ref)
        result: dict[str, Any] = {"command_ids": ids}
        if made:
            result["bound_by_this_call"] = made
        if wait:
            limit = min(timeout or self.settings.command_timeout, self.settings.command_timeout)
            await self._wait(ids, limit)
            result["commands"] = await self._statuses(client, ids)
        return self._with_notice(result, notice)

    async def command_status(self, command_ids: Sequence[str]) -> dict[str, Any]:
        """The status of commands this session ran, with their results once they ended."""
        client, notice = await self.client()
        return self._with_notice({"commands": await self._statuses(client, command_ids)}, notice)

    async def _statuses(self, client: Client, command_ids: Sequence[str]) -> list[dict[str, Any]]:
        statuses = []
        for command_id in command_ids:
            command = self._commands.get(command_id)
            entry: dict[str, Any] = {"command_id": command_id}
            if command is None:
                entry["status"] = "UNKNOWN"
                entry["hint"] = "not started by this session, or from a session that was lost"
            else:
                entry.update(
                    component_ref=command.ref,
                    command_type=command.command_type,
                    status=command.status,
                )
                if command.done.is_set() and command.status == "OK":
                    with contextlib.suppress(RoISError, TransportError):
                        results = await client.get_command_result(command_id)
                        if results:
                            entry["results"] = values.decode(results)
            statuses.append(entry)
        return statuses

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
        if command_type not in declared:
            raise AgentError(
                f"BAD_PARAMETER: {ref} has no command {command_type!r} "
                f"(commands: {', '.join(sorted(declared)) or 'none'})"
            )
        unit: dict[str, Any] = {"component_ref": ref, "command_type": command_type}
        arguments = command.get("arguments") or {}
        if not isinstance(arguments, Mapping):
            raise AgentError(f"step {index}: arguments must be an object of name to value")
        if arguments:
            try:
                unit["arguments"] = values.encode(arguments, declared[command_type].arguments)
            except values.ValueRefusedError as exc:
                raise AgentError(f"BAD_PARAMETER: {ref} {command_type} argument {exc}") from exc
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
            with contextlib.suppress(RoISError, TransportError):
                await client.release(ref)
            self._binds.pop(ref, None)

    def _track(self, command_id: str, ref: str, command_type: str) -> _Command:
        """Follow a command this session started, taking a completion that came first."""
        command = self._commands.setdefault(command_id, _Command(ref, command_type))
        status = self._early.pop(command_id, None)
        if status is not None:
            command.status = status
            command.done.set()
        return command

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
                self._binds.pop(ref, None)
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
        client, notice = await self.client()
        subscribe_id = await self._call(client.subscribe(event_type, component_ref(ref)), ref=ref)
        self._subscriptions[subscribe_id] = (ref, event_type)
        return self._with_notice(
            {
                "subscribe_id": subscribe_id,
                "component_ref": ref,
                "event_type": event_type,
                "cursor": self.events.last,
            },
            notice,
        )

    async def unsubscribe(self, subscribe_id: str) -> dict[str, Any]:
        """Cancel a subscription."""
        client, notice = await self.client()
        await self._call(client.unsubscribe(subscribe_id))
        self._subscriptions.pop(subscribe_id, None)
        return self._with_notice({"subscribe_id": subscribe_id, "unsubscribed": True}, notice)

    def get_events(self, since: int = 0, limit: int = 50) -> dict[str, Any]:
        """The buffered notifications after a cursor."""
        entries, cursor, dropped = self.events.since(since, limit)
        result: dict[str, Any] = {
            "entries": [entry.as_dict() for entry in entries],
            "cursor": cursor,
            "more": self.events.last > cursor,
        }
        if dropped:
            result["dropped"] = dropped
        return result

    async def wait_for_event(
        self,
        event_type: str = "",
        ref: str = "",
        timeout: float = 30.0,
        since: int | None = None,
    ) -> dict[str, Any]:
        """Wait for an event that matches, an error, or the timeout.

        Without ``since`` only notifications that arrive during the call count.
        """
        start = self.events.last if since is None else since

        def matches(entry: Entry) -> bool:
            if entry.kind in ("error", "connection_closed"):
                return True
            if entry.kind != "event":
                return False
            if event_type and entry.data.get("event_type") != event_type:
                return False
            return not ref or entry.data.get("component_ref") == ref

        limit = max(0.0, min(timeout, self.settings.command_timeout))
        found = await self.events.wait_for(start, matches, limit)
        if found is None:
            return {"timed_out": True, "cursor": self.events.last}
        return {"timed_out": False, "entry": found.as_dict(), "cursor": found.seq}

    async def get_error_detail(self, error_id: str) -> dict[str, Any]:
        """The details of an error from a notify_error entry."""
        client, notice = await self.client()
        results = await self._call(client.get_error_detail(error_id))
        return self._with_notice({"error_id": error_id, "results": values.decode(results)}, notice)

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

    async def _call[T](self, call: Awaitable[T], *, ref: str = "") -> T:
        """Await a RoIS call, turning a RoISError into a failure the agent can read."""
        try:
            return await call
        except RoISError as error:
            raise rois_failure(error, ref=ref) from error

    @staticmethod
    def _with_notice(result: dict[str, Any], notice: str | None) -> dict[str, Any]:
        if notice:
            result["notice"] = notice
        return result
