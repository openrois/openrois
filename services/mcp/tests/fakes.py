"""A stand-in for RoISClient that behaves like an engine with binds, for unit tests."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from openrois.interfaces import (
    CompletedParams,
    CompletedStatus,
    ErrorType,
    HRIComponentProfile,
    NotifyErrorParams,
    NotifyEventParams,
    Parameter,
    ProfileChangedParams,
    Result,
    ReturnCode,
)
from openrois.interfaces.profiles import (
    CommandMessageProfile,
    ComponentFunction,
    EventMessageProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from openrois.sdk import EngineProfile, RoISError
from openrois.sdk.errors import RoISConnectionError

from openrois.mcp.config import Settings


def _param(name: str, code: str, **extra: Any) -> ParameterProfile:
    return ParameterProfile(name=name, data_type_ref=RoISIdentifierType(code=code), **extra)


NAVIGATION = HRIComponentProfile(
    identifier=RoISIdentifierType(authority="OMG", code="Navigation"),
    name="navigation",
    function=ComponentFunction.ACTUATION,
    command_profiles=[
        CommandMessageProfile(name="start"),
        CommandMessageProfile(name="stop"),
        CommandMessageProfile(name="go", arguments=[_param("speed", "double")]),
    ],
    query_profiles=[
        QueryMessageProfile(name="component_status"),
        QueryMessageProfile(name="available_targets"),
    ],
    event_profiles=[EventMessageProfile(name="reached_target")],
    parameter_profiles=[
        _param("target_positions", "string[]", default_value="[]"),
        _param("time_limit", "int", default_value="0"),
        _param("model", "string", read_only=True),
    ],
)

PEOPLE = HRIComponentProfile(
    identifier=RoISIdentifierType(authority="OMG", code="PersonDetection"),
    name="person_detection",
    function=ComponentFunction.SENSING,
    query_profiles=[QueryMessageProfile(name="component_status")],
    event_profiles=[EventMessageProfile(name="person_detected", results=[_param("number", "int")])],
    parameter_profiles=[_param("threshold", "double", default_value="0.5")],
)

PROFILES = {"robot/navigation": NAVIGATION, "robot/person_detection": PEOPLE}


class Engine:
    """The state several fake clients share, as sessions of one engine."""

    def __init__(self) -> None:
        self.holders: dict[str, set[int]] = defaultdict(set)
        self.next_id = 0
        self.executed: list[Sequence[Any]] = []
        self.released: list[tuple[int, str]] = []
        self.parameters: dict[str, list[Parameter]] = {
            "robot/person_detection": [
                Parameter(name="threshold", data_type_ref="double", value="0.5")
            ],
            "robot/navigation": [
                Parameter(name="target_positions", data_type_ref="string[]", value="[]")
            ],
        }
        #: Return codes to fail the next bind of a ref with, for tests that force it.
        self.fail_bind: dict[str, ReturnCode] = {}
        #: How each command ends, by command_type. None leaves it running.
        self.outcome: dict[str, str | None] = defaultdict(lambda: "OK")
        #: An error to notify, by command_type, just before the command ends.
        self.error_on: dict[str, str] = {}
        #: Commands still running: command id to session and ref.
        self.running: dict[str, tuple[int, str]] = {}
        #: Running commands a release does not abort, as a command waiting its turn in a
        #: sequence.
        self.queued: set[str] = set()
        #: Components the engine does not list, as when their engine left.
        self.hidden: set[str] = set()
        #: Components whose queries and subscribes answer ERROR, as a device that is gone.
        self.inoperable: set[str] = set()
        #: Answer set_parameter with BAD_PARAMETER, as a component that refuses the value.
        self.refuse_values = False
        #: Make execute never answer, for tests of a gateway that hangs.
        self.hang_execute = False
        self.sessions: list[FakeClient] = []

    def new_id(self, prefix: str) -> str:
        self.next_id += 1
        return f"robot/{prefix}-{self.next_id}"

    def engine_left(self, refs: Sequence[str], *, notify: bool = True) -> None:
        """Drop every bind and subscription on refs, as when their engine leaves the gateway.

        The gateway then sends profile_changed, unless notify is False.
        """
        for ref in refs:
            self.holders[ref].clear()
        for client in self.sessions:
            for subscribe_id, ref in list(client.subscription_refs.items()):
                if ref in refs:
                    client.subscriptions.pop(subscribe_id, None)
                    client.subscription_refs.pop(subscribe_id, None)
            if notify and not client.closed:
                client.emit("rois.system.profile_changed", ProfileChangedParams())


class FakeClient:
    """One session on a fake Engine."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.session = len(engine.sessions) + 1
        engine.sessions.append(self)
        self.listeners: dict[str, list[Callable[..., object]]] = defaultdict(list)
        self.closed = False
        self.disconnected = False
        self.subscriptions: dict[str, str] = {}
        self.subscription_refs: dict[str, str] = {}
        self.unsubscribed: list[str] = []

    # The listener API ------------------------------------------------------

    def on(self, name: str, listener: Callable[..., object]) -> FakeClient:
        self.listeners[name].append(listener)
        return self

    def emit(self, name: str, *args: object) -> None:
        for listener in self.listeners[name]:
            listener(*args)

    def drop(self) -> None:
        """Lose the connection, as a gateway restart would."""
        self.closed = True
        for holders in self.engine.holders.values():
            holders.discard(self.session)
        self.emit("close", 1006, "gone")

    # RoIS ------------------------------------------------------------------

    def _check_open(self) -> None:
        if self.closed:
            raise RoISConnectionError("closed")

    async def disconnect(self) -> None:
        self.disconnected = True
        self.closed = True
        for holders in self.engine.holders.values():
            holders.discard(self.session)

    async def get_profile(self, condition: str = "") -> EngineProfile:
        self._check_open()
        from openrois.interfaces import HRIEngineProfileType

        selected = {
            ref: profile
            for ref, profile in PROFILES.items()
            if ref not in self.engine.hidden
            and (not condition or ref.split("/")[0] in condition or ref in condition)
        }
        engine = HRIEngineProfileType(
            identifier=RoISIdentifierType(code="Engine"), component_ids=list(selected)
        )
        return EngineProfile(engine, selected)

    async def get_error_detail(self, error_id: str, condition: str = "") -> list[Result]:
        return [Result(name="detail", data_type_ref="string", value=f"about {error_id}")]

    def _check_listed(self, component_ref: str, method: str) -> None:
        if component_ref in self.engine.hidden:
            raise RoISError(ReturnCode.UNSUPPORTED, method)

    async def bind(self, component_ref: str) -> None:
        self._check_open()
        self._check_listed(component_ref, "rois.command.bind")
        code = self.engine.fail_bind.pop(component_ref, None)
        if code is not None:
            raise RoISError(code, "rois.command.bind")
        holders = self.engine.holders[component_ref]
        if (
            PROFILES[component_ref].function is ComponentFunction.ACTUATION
            and holders
            and self.session not in holders
        ):
            raise RoISError(ReturnCode.OUT_OF_RESOURCES, "rois.command.bind")
        holders.add(self.session)

    async def release(self, component_ref: str) -> None:
        self._check_open()
        self._check_listed(component_ref, "rois.command.release")
        self.engine.holders[component_ref].discard(self.session)
        self.engine.released.append((self.session, component_ref))
        # A release aborts the session's commands running on the component.
        loop = asyncio.get_running_loop()
        for command_id, (session, ref) in list(self.engine.running.items()):
            if session == self.session and ref == component_ref:
                if command_id in self.engine.queued:
                    continue
                del self.engine.running[command_id]
                loop.call_soon(self._complete, command_id, "ABORT")

    def _complete(self, command_id: str, status: str) -> None:
        completed = CompletedParams(command_id=command_id, status=CompletedStatus(status))
        self.emit("rois.command.completed", completed)

    def notify_error(self, error_id: str) -> None:
        """Send a notify_error to this session."""
        self.emit(
            "rois.system.notify_error",
            NotifyErrorParams(error_id=error_id, error_type=ErrorType.COMPONENT_INTERNAL_ERROR),
        )

    def _require_bind(self, component_ref: str, method: str) -> None:
        if self.session not in self.engine.holders[component_ref]:
            raise RoISError(ReturnCode.ERROR, method)

    async def get_parameter(self, component_ref: str) -> list[Parameter]:
        self._check_listed(component_ref, "rois.command.get_parameter")
        self._require_bind(component_ref, "rois.command.get_parameter")
        # A real call waits for the reply, which lets other tool calls run meanwhile.
        await asyncio.sleep(0)
        return self.engine.parameters.get(component_ref, [])

    async def set_parameter(
        self, component_ref: str, parameters: Sequence[Parameter | Mapping[str, Any]]
    ) -> str:
        self._require_bind(component_ref, "rois.command.set_parameter")
        if self.engine.refuse_values:
            raise RoISError(ReturnCode.BAD_PARAMETER, "rois.command.set_parameter")
        command_id = self.engine.new_id("param")
        # The completion comes before the reply, as it can on a real engine.
        completed = CompletedParams(command_id=command_id, status=CompletedStatus.OK)
        self.emit("rois.command.completed", completed)
        return command_id

    async def execute(self, command_unit_list: Sequence[Any]) -> list[str]:
        self._check_open()
        if self.engine.hang_execute:
            await asyncio.Event().wait()
        units: list[Mapping[str, Any]] = []
        for item in command_unit_list:
            if "branch_list" in item:
                for branch in item["branch_list"]:
                    units.extend(branch["command_list"])
            else:
                units.append(item)
        for unit in units:
            self._require_bind(unit["component_ref"], "rois.command.execute")
        self.engine.executed.append(command_unit_list)
        ids = [self.engine.new_id("cmd") for _ in units]
        loop = asyncio.get_running_loop()
        for command_id, unit in zip(ids, units, strict=True):
            status = self.engine.outcome[unit["command_type"]]
            error_id = self.engine.error_on.get(unit["command_type"])
            if error_id is not None:
                loop.call_soon(self.notify_error, error_id)
            if status is None:
                self.engine.running[command_id] = (self.session, unit["component_ref"])
            else:
                loop.call_soon(self._complete, command_id, status)
        return ids

    async def get_command_result(self, command_id: str, condition: str = "") -> list[Result]:
        return []

    async def query(self, query_type: str, condition: str = "") -> list[Result]:
        self._check_open()
        ref = condition.split("'")[1]
        if ref in self.engine.inoperable and query_type != "component_status":
            raise RoISError(ReturnCode.ERROR, "rois.query.query")
        if query_type == "component_status":
            others = self.engine.holders[ref] - {self.session}
            busy = PROFILES[ref].function is ComponentFunction.ACTUATION and others
            return [
                Result(
                    name="status",
                    data_type_ref="Component_Status",
                    value="BUSY" if busy else "READY",
                )
            ]
        raise RoISError(ReturnCode.UNSUPPORTED, "rois.query.query")

    async def subscribe(self, event_type: str, condition: str = "") -> str:
        self._check_open()
        ref = condition.split("'")[1]
        if ref in self.engine.inoperable:
            raise RoISError(ReturnCode.ERROR, "rois.event.subscribe")
        subscribe_id = self.engine.new_id("sub")
        self.subscriptions[subscribe_id] = event_type
        self.subscription_refs[subscribe_id] = ref
        return subscribe_id

    async def unsubscribe(self, subscribe_id: str) -> None:
        self.subscriptions.pop(subscribe_id, None)
        self.subscription_refs.pop(subscribe_id, None)
        self.unsubscribed.append(subscribe_id)

    def fire(self, subscribe_id: str, number: int) -> None:
        """Send a person_detected occurrence to this session."""
        self.emit(
            "rois.event.notify_event",
            NotifyEventParams(
                event_id=self.engine.new_id("evt"),
                event_type=self.subscriptions[subscribe_id],
                subscribe_id=subscribe_id,
                results=[Result(name="number", data_type_ref="int", value=str(number))],
            ),
        )


def factory_for(engine: Engine) -> Callable[[Settings], Any]:
    """A ClientFactory that opens a new FakeClient session on the engine."""

    async def open_client(_settings: Settings) -> FakeClient:
        return FakeClient(engine)

    return open_client
