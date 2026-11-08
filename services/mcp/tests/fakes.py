"""A stand-in for RoISClient that behaves like an engine with binds, for unit tests."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from openrois.interfaces import (
    CompletedParams,
    CompletedStatus,
    HRIComponentProfile,
    NotifyEventParams,
    Parameter,
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
    query_profiles=[QueryMessageProfile(name="component_status")],
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
        self.sessions: list[FakeClient] = []

    def new_id(self, prefix: str) -> str:
        self.next_id += 1
        return f"robot/{prefix}-{self.next_id}"


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
            if not condition or ref.split("/")[0] in condition or ref in condition
        }
        engine = HRIEngineProfileType(
            identifier=RoISIdentifierType(code="Engine"), component_ids=list(selected)
        )
        return EngineProfile(engine, selected)

    async def get_error_detail(self, error_id: str, condition: str = "") -> list[Result]:
        return [Result(name="detail", data_type_ref="string", value=f"about {error_id}")]

    async def bind(self, component_ref: str) -> None:
        self._check_open()
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
        self.engine.holders[component_ref].discard(self.session)
        self.engine.released.append((self.session, component_ref))

    def _require_bind(self, component_ref: str, method: str) -> None:
        if self.session not in self.engine.holders[component_ref]:
            raise RoISError(ReturnCode.ERROR, method)

    async def get_parameter(self, component_ref: str) -> list[Parameter]:
        self._require_bind(component_ref, "rois.command.get_parameter")
        return self.engine.parameters.get(component_ref, [])

    async def set_parameter(
        self, component_ref: str, parameters: Sequence[Parameter | Mapping[str, Any]]
    ) -> str:
        self._require_bind(component_ref, "rois.command.set_parameter")
        command_id = self.engine.new_id("param")
        # The completion comes before the reply, as it can on a real engine.
        completed = CompletedParams(command_id=command_id, status=CompletedStatus.OK)
        self.emit("rois.command.completed", completed)
        return command_id

    async def execute(self, command_unit_list: Sequence[Any]) -> list[str]:
        self._check_open()
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
            if status is not None:
                loop.call_soon(
                    self.emit,
                    "rois.command.completed",
                    CompletedParams(command_id=command_id, status=CompletedStatus(status)),
                )
        return ids

    async def get_command_result(self, command_id: str, condition: str = "") -> list[Result]:
        return []

    async def query(self, query_type: str, condition: str = "") -> list[Result]:
        self._check_open()
        ref = condition.split("'")[1]
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
        subscribe_id = self.engine.new_id("sub")
        self.subscriptions[subscribe_id] = event_type
        return subscribe_id

    async def unsubscribe(self, subscribe_id: str) -> None:
        self.subscriptions.pop(subscribe_id, None)

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
