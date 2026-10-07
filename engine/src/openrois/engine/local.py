"""The components an engine hosts in its own process.

``LocalComponents`` implements the component contract for components that live in the
engine's process, written with ``openrois-components-core`` or with any class of the
same shape (``LocalComponent``). It keeps what the components do not have to: the
parameter store, the running commands and their results, the subscriptions and the
recent events. It also answers ``component_status`` from the state of each component.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from openrois.interfaces.catalog import (
    GetCommandResultResult,
    GetErrorDetailResult,
    GetEventDetailResult,
    GetParameterResult,
    QueryResult,
    SetParameterResult,
    SubscribeResult,
)
from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.hri import Argument, CommandUnit, Parameter, Result, ReturnCode
from openrois.interfaces.profiles import HRIComponentProfile, HRIEngineProfileType
from openrois.interfaces.service import CompletedStatus, NotifyEventParams

from openrois.engine.contract import Deliver, OnCompleted

logger = logging.getLogger(__name__)

# How many finished commands keep their results for get_command_result.
_RESULTS_KEPT = 4096

_STATUS_QUERY = "component_status"


class ComponentBinding(Protocol):
    """What the engine gives each local component when it hosts it."""

    @property
    def ref(self) -> str:
        """The fully qualified ref of the component, ``engine_id/name``."""
        ...

    def parameters(self) -> Sequence[Parameter]:
        """The current value of every parameter of the component."""
        ...

    def emit(self, event_type: str, results: Sequence[Result]) -> None:
        """Send an event to its subscriptions. Safe to call from any thread."""
        ...


class LocalComponent(Protocol):
    """A component the engine hosts in its process.

    ``Component`` from ``openrois-components-core`` has this shape. A command or a
    parameter hook that raises an exception with a ``status`` attribute, such as
    ``CommandFailed``, ends with that status, and any other exception with ERROR.
    """

    def rois_profile(self) -> HRIComponentProfile:
        """The profile the component serves: the messages it implements."""
        ...

    def rois_bind(self, binding: ComponentBinding) -> None:
        """Receive the binding to the engine that hosts the component."""
        ...

    async def rois_command(self, command_type: str, arguments: Sequence[Argument]) -> list[Result]:
        """Run one command until it ends, and return its results."""
        ...

    async def rois_query(self, query_type: str) -> list[Result]:
        """Answer one query."""
        ...

    async def rois_subscribed(self, event_type: str) -> None:
        """Prepare for a new subscription to an event."""
        ...

    async def rois_set_parameters(self, parameters: Sequence[Parameter]) -> None:
        """Apply new parameter values, or raise to refuse them."""
        ...

    async def connect(self) -> None:
        """Open the connection to the backend."""
        ...

    async def disconnect(self) -> None:
        """Close the connection to the backend."""
        ...


class _State(Enum):
    UNINITIALIZED = "uninitialized"
    READY = "ready"
    FAILED = "failed"


@dataclass(eq=False)
class _Start:
    """A start command: its id, and its handler once it runs."""

    command_id: str
    task: asyncio.Task[list[Result]] | None = None


@dataclass(eq=False)
class _Hosted:
    """One local component and what the engine keeps for it."""

    name: str
    ref: str
    component: LocalComponent
    profile: HRIComponentProfile
    parameters: dict[str, Parameter]
    state: _State = _State.UNINITIALIZED
    running: dict[str, asyncio.Task[list[Result]]] = field(default_factory=dict)
    # The latest start command, which stop and a new start abort.
    start: _Start | None = None
    # Commands that end with ABORT however their handler finishes.
    aborted: set[str] = field(default_factory=set)
    # Held while a start halts the start before it, so starts take turns and a start
    # never runs its handler next to the one it replaces. A stop never waits for it.
    takeover: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass(frozen=True, slots=True)
class _Subscription:
    ref: str
    event_type: str
    deliver: Deliver


class _Binding:
    """The binding of one component to the engine that hosts it."""

    def __init__(self, source: LocalComponents, ref: str) -> None:
        self._source = source
        self._ref = ref

    @property
    def ref(self) -> str:
        return self._ref

    def parameters(self) -> Sequence[Parameter]:
        return list(self._source.hosted(self._ref).parameters.values())

    def emit(self, event_type: str, results: Sequence[Result]) -> None:
        self._source.emit(self._ref, event_type, list(results))


class LocalComponents:
    """The component contract for the components of this process."""

    def __init__(self, engine_id: str, *, event_lifetime: float = 60.0) -> None:
        """Initialize an empty set of components.

        Args:
            engine_id: The id of the engine that hosts the components.
            event_lifetime: Seconds that get_event_detail keeps an event after its
                notification.
        """
        self._engine_id = engine_id
        self._event_lifetime = timedelta(seconds=event_lifetime)
        self._hosted: dict[str, _Hosted] = {}
        self._subscriptions: dict[str, _Subscription] = {}
        self._events: dict[str, tuple[list[Result], datetime]] = {}
        self._results: dict[str, list[Result]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._next_id = 0

    # -- Hosting -------------------------------------------------------------------------

    def add(self, name: str, component: LocalComponent) -> str:
        """Host a component under ``name`` and return its ref, ``engine_id/name``.

        Raises:
            ValueError: The name is empty, contains a slash, or is taken.
        """
        if not name or "/" in name:
            raise ValueError(f"A component name must be non-empty and free of slashes: {name!r}")
        ref = f"{self._engine_id}/{name}"
        if ref in self._hosted:
            raise ValueError(f"A component named {name!r} is already hosted")
        profile = component.rois_profile().model_copy(update={"name": name})
        parameters = {
            p.name: Parameter(
                name=p.name, data_type_ref=p.data_type_ref.code, value=p.default_value
            )
            for p in profile.parameter_profiles
        }
        self._hosted[ref] = _Hosted(name, ref, component, profile, parameters)
        component.rois_bind(_Binding(self, ref))
        return ref

    def hosted(self, ref: str) -> _Hosted:
        """The hosted component of a ref."""
        return self._hosted[ref]

    def components(self) -> list[LocalComponent]:
        """Every hosted component, in the order they were added."""
        return [hosted.component for hosted in self._hosted.values()]

    async def start(self) -> None:
        """Connect every component. A component whose connect() fails reports ERROR."""
        self._loop = asyncio.get_running_loop()
        for hosted in self._hosted.values():
            try:
                await hosted.component.connect()
            except Exception:
                logger.exception("%s could not connect to its backend", hosted.ref)
                hosted.state = _State.FAILED
            else:
                hosted.state = _State.READY

    async def stop(self) -> None:
        """Cancel every running command and disconnect every component."""
        tasks: list[asyncio.Task[object]] = [*self._tasks]
        for hosted in self._hosted.values():
            tasks.extend(hosted.running.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for hosted in self._hosted.values():
            if hosted.state is _State.READY:
                try:
                    await hosted.component.disconnect()
                except Exception:
                    logger.exception("%s could not disconnect from its backend", hosted.ref)
            hosted.state = _State.UNINITIALIZED
        self._subscriptions.clear()

    def status(self, ref: str) -> ComponentStatus:
        """The status of a component, as component_status reports it."""
        hosted = self._hosted[ref]
        if hosted.state is _State.UNINITIALIZED:
            return ComponentStatus.UNINITIALIZED
        if hosted.state is _State.FAILED:
            return ComponentStatus.ERROR
        return ComponentStatus.BUSY if hosted.running else ComponentStatus.READY

    # -- The component contract ----------------------------------------------------------

    @property
    def engine_ids(self) -> frozenset[str]:
        return frozenset({self._engine_id})

    def profiles(self) -> Mapping[str, HRIComponentProfile]:
        return {ref: hosted.profile for ref, hosted in self._hosted.items()}

    def engine_profile(self) -> HRIEngineProfileType | None:
        return None

    async def run(self, unit: CommandUnit) -> CompletedStatus:
        hosted = self._hosted[unit.component_ref]
        if unit.command_type == "set_parameter":
            parameters = [_parameter(hosted, a.name, a.value) for a in unit.arguments]
            status = await self._apply(hosted, parameters)
            self._keep(unit.command_id, [])
            return status
        if hosted.state is not _State.READY:
            self._keep(unit.command_id, [])
            return CompletedStatus.ERROR
        if unit.command_type == "start":
            return await self._start(hosted, unit)
        if unit.command_type == "stop":
            return await self._stop(hosted, unit)
        return await self._end(hosted, unit, self._begin(hosted, unit))

    async def set_parameter(
        self,
        ref: str,
        parameters: Sequence[Parameter],
        on_completed: OnCompleted,
    ) -> SetParameterResult:
        hosted = self._hosted[ref]
        command_id = self._new_id("param")
        self._keep(command_id, [])

        async def apply() -> None:
            on_completed(command_id, await self._apply(hosted, parameters))

        self._spawn(apply())
        return SetParameterResult(return_code=ReturnCode.OK, command_id=command_id)

    async def get_parameter(self, ref: str) -> GetParameterResult:
        stored = self._hosted[ref].parameters.values()
        return GetParameterResult(
            return_code=ReturnCode.OK,
            parameters=[p for p in stored if p.value != ""],
        )

    async def command_result(self, command_id: str) -> GetCommandResultResult:
        if command_id not in self._results:
            return GetCommandResultResult(return_code=ReturnCode.BAD_PARAMETER)
        return GetCommandResultResult(return_code=ReturnCode.OK, results=self._results[command_id])

    async def query(self, ref: str, query_type: str) -> QueryResult:
        hosted = self._hosted[ref]
        if query_type == _STATUS_QUERY:
            status = Result(name="status", data_type_ref="Component_Status", value=self.status(ref))
            return QueryResult(return_code=ReturnCode.OK, results=[status])
        if hosted.state is not _State.READY:
            return QueryResult(return_code=ReturnCode.ERROR)
        try:
            results = await hosted.component.rois_query(query_type)
        except Exception:
            logger.exception("%s failed to answer %s", ref, query_type)
            return QueryResult(return_code=ReturnCode.ERROR)
        return QueryResult(return_code=ReturnCode.OK, results=results)

    async def subscribe(self, ref: str, event_type: str, deliver: Deliver) -> SubscribeResult:
        hosted = self._hosted[ref]
        if hosted.state is not _State.READY:
            return SubscribeResult(return_code=ReturnCode.ERROR)
        try:
            await hosted.component.rois_subscribed(event_type)
        except Exception:
            logger.exception("%s failed to start the subscription to %s", ref, event_type)
            return SubscribeResult(return_code=ReturnCode.ERROR)
        # The subscription takes events from here on, so its first event cannot reach
        # the client before the reply that names it.
        subscribe_id = self._new_id("sub")
        self._subscriptions[subscribe_id] = _Subscription(ref, event_type, deliver)
        return SubscribeResult(return_code=ReturnCode.OK, subscribe_id=subscribe_id)

    async def unsubscribe(self, subscribe_id: str) -> None:
        self._subscriptions.pop(subscribe_id, None)

    async def event_detail(self, event_id: str) -> GetEventDetailResult:
        self._prune_events()
        event = self._events.get(event_id)
        if event is None:
            return GetEventDetailResult(return_code=ReturnCode.BAD_PARAMETER)
        return GetEventDetailResult(return_code=ReturnCode.OK, results=event[0])

    async def error_detail(self, error_id: str) -> GetErrorDetailResult:
        # Local components report no engine errors yet, so no error_id is known.
        return GetErrorDetailResult(return_code=ReturnCode.BAD_PARAMETER)

    # -- Events --------------------------------------------------------------------------

    def emit(self, ref: str, event_type: str, results: list[Result]) -> None:
        """Publish an event of a component, from any thread."""
        loop = self._loop
        if loop is None:
            logger.warning("%s emitted %s before the engine started. Dropped.", ref, event_type)
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._publish(ref, event_type, results)
            return
        try:
            loop.call_soon_threadsafe(self._publish, ref, event_type, results)
        except RuntimeError:
            logger.warning("%s emitted %s after the engine stopped. Dropped.", ref, event_type)

    def _publish(self, ref: str, event_type: str, results: list[Result]) -> None:
        """Send one event to its subscriptions and keep it for get_event_detail."""
        subscriptions = [
            (subscribe_id, s)
            for subscribe_id, s in self._subscriptions.items()
            if s.ref == ref and s.event_type == event_type
        ]
        if not subscriptions:
            return
        self._prune_events()
        event_id = self._new_id("evt")
        expires = datetime.now(UTC) + self._event_lifetime
        self._events[event_id] = (results, expires)
        for subscribe_id, subscription in subscriptions:
            subscription.deliver(
                NotifyEventParams(
                    event_id=event_id,
                    event_type=event_type,
                    subscribe_id=subscribe_id,
                    expire=expires.isoformat(),
                    results=results,
                )
            )

    def _prune_events(self) -> None:
        now = datetime.now(UTC)
        for event_id in [e for e, (_, expires) in self._events.items() if expires < now]:
            del self._events[event_id]

    # -- Commands ------------------------------------------------------------------------

    def _begin(self, hosted: _Hosted, unit: CommandUnit) -> asyncio.Task[list[Result]]:
        """Start the handler of one command as a task."""
        # A running command has no results yet, and get_command_result says so.
        self._keep(unit.command_id, [])
        task = asyncio.create_task(hosted.component.rois_command(unit.command_type, unit.arguments))
        hosted.running[unit.command_id] = task
        return task

    async def _end(
        self, hosted: _Hosted, unit: CommandUnit, task: asyncio.Task[list[Result]]
    ) -> CompletedStatus:
        """Wait until a command ends, within the timeout of its profile, and keep its results."""
        results: list[Result] = []
        try:
            try:
                async with asyncio.timeout(_timeout(hosted, unit.command_type)):
                    results = await task
            except TimeoutError:
                status = CompletedStatus.TIMEOUT
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                status = CompletedStatus.ABORT
            except Exception as exc:
                status = _failure_status(exc)
                if status is CompletedStatus.ERROR:
                    logger.exception("%s failed to run %s", hosted.ref, unit.command_type)
            else:
                status = CompletedStatus.OK
            if unit.command_id in hosted.aborted:
                status = CompletedStatus.ABORT
        finally:
            hosted.running.pop(unit.command_id, None)
            hosted.aborted.discard(unit.command_id)
            if hosted.start is not None and hosted.start.command_id == unit.command_id:
                hosted.start = None
        self._keep(unit.command_id, results if status is CompletedStatus.OK else [])
        return status

    async def _start(self, hosted: _Hosted, unit: CommandUnit) -> CompletedStatus:
        """Run a start, after the start before it ended with ABORT."""
        # The new start replaces the latest one at once, so a stop or a later start that
        # arrives while this one waits for its turn aborts this one.
        previous = hosted.start
        current = _Start(unit.command_id)
        hosted.start = current
        if previous is not None:
            hosted.aborted.add(previous.command_id)
        try:
            async with hosted.takeover:
                if previous is not None and previous.task is not None:
                    await self._halt(hosted, previous.task)
                if unit.command_id in hosted.aborted:
                    self._keep(unit.command_id, [])
                    return CompletedStatus.ABORT
                current.task = self._begin(hosted, unit)
        finally:
            if current.task is None:
                hosted.aborted.discard(unit.command_id)
                if hosted.start is current:
                    hosted.start = None
        return await self._end(hosted, unit, current.task)

    async def _stop(self, hosted: _Hosted, unit: CommandUnit) -> CompletedStatus:
        """Run the stop handler at once, then cancel the latest start."""
        current = hosted.start
        if current is not None:
            # The start ends with ABORT even if halting the backend ends it first.
            hosted.aborted.add(current.command_id)
        status = await self._end(hosted, unit, self._begin(hosted, unit))
        if current is not None and current.task is not None:
            current.task.cancel()
        return status

    async def _halt(self, hosted: _Hosted, task: asyncio.Task[list[Result]]) -> None:
        """Run the stop handler, within its timeout, then cancel a start and wait for it."""
        if not task.done() and any(m.name == "stop" for m in hosted.profile.command_profiles):
            try:
                async with asyncio.timeout(_timeout(hosted, "stop")):
                    await hosted.component.rois_command("stop", [])
            except Exception:
                logger.exception("%s failed to stop before a new start", hosted.ref)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _apply(self, hosted: _Hosted, parameters: Sequence[Parameter]) -> CompletedStatus:
        """Run the parameter hook and store the new values if it accepts them."""
        if hosted.state is not _State.READY:
            return CompletedStatus.ERROR
        try:
            await hosted.component.rois_set_parameters(parameters)
        except Exception as exc:
            status = _failure_status(exc)
            logger.warning("%s refused new parameter values: %s", hosted.ref, exc)
            return status
        for parameter in parameters:
            hosted.parameters[parameter.name] = _parameter(hosted, parameter.name, parameter.value)
        return CompletedStatus.OK

    def _keep(self, command_id: str, results: list[Result]) -> None:
        self._results.pop(command_id, None)
        self._results[command_id] = results
        while len(self._results) > _RESULTS_KEPT:
            del self._results[next(iter(self._results))]

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _new_id(self, kind: str) -> str:
        self._next_id += 1
        return f"{self._engine_id}/{kind}-{self._next_id}"


def _timeout(hosted: _Hosted, command_type: str) -> float | None:
    """The timeout of a command in seconds, from its profile, or None for no timeout."""
    message = next(m for m in hosted.profile.command_profiles if m.name == command_type)
    return message.timeout / 1000 if message.timeout else None


def _parameter(hosted: _Hosted, name: str, value: str) -> Parameter:
    """A parameter value with the type its profile gives it."""
    code = next(p.data_type_ref.code for p in hosted.profile.parameter_profiles if p.name == name)
    return Parameter(name=name, data_type_ref=code, value=value)


def _failure_status(exc: BaseException) -> CompletedStatus:
    """The status a failed command ends with: the one its exception names, or ERROR."""
    status = getattr(exc, "status", None)
    if isinstance(status, str):
        try:
            named = CompletedStatus(status)
        except ValueError:
            return CompletedStatus.ERROR
        if named is not CompletedStatus.OK:
            return named
    return CompletedStatus.ERROR
