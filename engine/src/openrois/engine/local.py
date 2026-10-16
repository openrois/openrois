"""The components an engine hosts in its own process.

``LocalComponents`` implements the component contract for components that live in the
engine's process, written with ``openrois-components-core`` or with any class of the
same shape (``LocalComponent``). It keeps what the components do not have to: the
resources they share, the parameter store, the running commands and their results, the
subscriptions and the recent events, and the statuses raised on the components and on
the engine with the errors they cause. It answers ``component_status`` from the
lifecycle and the raised status of each component.

It also gives every component whose profile includes RoISCommon the RoIS_Common default
(OpenRoIS First Release, questions 8 and 9). A component is started from the moment a
start begins until stop, or until that start ends other than OK. On a component that is
not started, suspend, resume and stop complete OK and run no handler. suspend holds
start and every other function command of the component, which wait without starting
until resume, or end with TIMEOUT when their profile timeout elapses, while
set_parameter applies at once and the component's events are dropped. stop ends the
suspension and the held commands end with ABORT. A handler adds to this: suspend's runs
after the hold, resume's before the release, and stop's as before.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from functools import partial
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
from openrois.interfaces.components import ROIS_COMMON_URN
from openrois.interfaces.hri import Argument, CommandUnit, Parameter, Result, ReturnCode
from openrois.interfaces.profiles import HRIComponentProfile, HRIEngineProfileType
from openrois.interfaces.service import CompletedStatus, ErrorType, NotifyEventParams

from openrois.engine.contract import Deliver, OnError

logger = logging.getLogger(__name__)

# How many finished commands keep their results for get_command_result.
_RESULTS_KEPT = 4096

_STATUS_QUERY = "component_status"

# The RoIS_Common commands that complete OK, running no handler, on a component that is
# not started.
_UNSTARTED_NO_OPS = frozenset({"suspend", "resume", "stop"})


class _Refused(Enum):
    """A component's parameter hook refused new values."""

    REFUSED = "refused"


_REFUSED = _Refused.REFUSED

# The statuses a component, a resource or the engine may raise.
_RAISABLE = frozenset({ComponentStatus.WARNING, ComponentStatus.ERROR})


class ResourceBinding(Protocol):
    """What the engine gives each resource it opens."""

    def raise_status(self, status: ComponentStatus, message: str) -> None:
        """Report WARNING or ERROR on every component that uses the resource."""
        ...

    def clear_status(self) -> None:
        """Withdraw the status the resource raised."""
        ...


class LocalResource(Protocol):
    """Something several local components share. ``Resource`` has this shape."""

    async def open(self) -> None:
        """Open what the resource holds."""
        ...

    async def close(self) -> None:
        """Close what the resource holds."""
        ...

    def rois_bind(self, binding: ResourceBinding) -> None:
        """Receive the binding to the engine that opens the resource."""
        ...


class ComponentBinding(Protocol):
    """What the engine gives each local component when it hosts it."""

    @property
    def ref(self) -> str:
        """The fully qualified ref of the component, ``engine_id/name``."""
        ...

    def parameters(self) -> Sequence[Parameter]:
        """The current value of every parameter of the component."""
        ...

    def emit(
        self,
        event_type: str,
        results: Sequence[Result],
        concerning: Mapping[str, str] | None = None,
    ) -> None:
        """Send an event to its subscriptions. Safe to call from any thread.

        ``concerning`` names the argument values the event is about.
        """
        ...

    def raise_status(self, status: ComponentStatus, message: str) -> None:
        """Report WARNING or ERROR for the component. Safe to call from any thread."""
        ...

    def clear_status(self) -> None:
        """Withdraw the status the component raised. Safe to call from any thread."""
        ...

    def engine_status(self) -> ComponentStatus:
        """The status of the engine: ERROR or WARNING as raised on it, or READY."""
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

    def rois_resources(self) -> Sequence[LocalResource]:
        """The resources the component uses, which the engine opens before connect()."""
        ...

    async def rois_command(self, command_type: str, arguments: Sequence[Argument]) -> list[Result]:
        """Run one command until it ends, and return its results."""
        ...

    async def rois_query(self, query_type: str, arguments: Sequence[Argument]) -> list[Result]:
        """Answer one query with the arguments its condition gave."""
        ...

    async def rois_subscribed(self, event_type: str, arguments: Sequence[Argument]) -> None:
        """Prepare for a new subscription to an event, with the arguments it gave."""
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


@dataclass(frozen=True, slots=True)
class _Raised:
    """A status raised by one source, and the errors it caused that are still kept."""

    status: ComponentStatus
    message: str
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Error:
    """The detail of an error, kept for get_error_detail until it is cleared."""

    ref: str
    status: ComponentStatus
    message: str
    time: datetime


@dataclass(eq=False)
class _Start:
    """A start command: its id, and its handler once it runs."""

    command_id: str
    task: asyncio.Task[list[Result]] | None = None


@dataclass(eq=False)
class _Suspension:
    """One suspension of a component, which the commands it holds wait on."""

    released: asyncio.Event = field(default_factory=asyncio.Event)
    # Set by a stop: the commands held end with ABORT instead of running.
    aborted: bool = False


@dataclass(eq=False)
class _Hosted:
    """One local component and what the engine keeps for it."""

    name: str
    ref: str
    component: LocalComponent
    profile: HRIComponentProfile
    parameters: dict[str, Parameter]
    resources: list[LocalResource]
    state: _State = _State.UNINITIALIZED
    # The raised statuses, by the source that raised them: the component itself, or
    # one of its resources.
    raised: dict[object, _Raised] = field(default_factory=dict)
    running: dict[str, asyncio.Task[list[Result]]] = field(default_factory=dict)
    # The latest start command, which stop and a new start abort.
    start: _Start | None = None
    # Commands that end with ABORT however their handler finishes.
    aborted: set[str] = field(default_factory=set)
    # Held while a start halts the start before it, so starts take turns and a start
    # never runs its handler next to the one it replaces. A stop never waits for it.
    takeover: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Whether the profile includes RoISCommon, which gives the component the default.
    rois_common: bool = False
    # Whether a start began since the last stop and has not failed.
    started: bool = False
    # The suspension in force, if any.
    suspension: _Suspension | None = None


@dataclass(frozen=True, slots=True)
class _Subscription:
    ref: str
    event_type: str
    arguments: Mapping[str, str]
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

    def emit(
        self,
        event_type: str,
        results: Sequence[Result],
        concerning: Mapping[str, str] | None = None,
    ) -> None:
        self._source.emit(self._ref, event_type, list(results), dict(concerning or {}))

    def raise_status(self, status: ComponentStatus, message: str) -> None:
        _check_raisable(status)
        self._source.call(
            self._source.raise_component_status, self._ref, self, status, message
        )

    def clear_status(self) -> None:
        self._source.call(self._source.clear_component_status, self._ref, self)

    def engine_status(self) -> ComponentStatus:
        return self._source.engine_status()


class _ResourceBinding:
    """The binding of one resource to the engine that opens it."""

    def __init__(self, source: LocalComponents, resource: LocalResource) -> None:
        self._source = source
        self._resource = resource

    def raise_status(self, status: ComponentStatus, message: str) -> None:
        _check_raisable(status)
        self._source.call(self._source.raise_resource_status, self._resource, status, message)

    def clear_status(self) -> None:
        self._source.call(self._source.clear_resource_status, self._resource)


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
        # Every resource of the hosted components, once, in the order first used.
        self._resources: list[LocalResource] = []
        self._opened: list[LocalResource] = []
        self._subscriptions: dict[str, _Subscription] = {}
        self._events: dict[str, tuple[list[Result], datetime]] = {}
        self._results: dict[str, list[Result]] = {}
        self._errors: dict[str, _Error] = {}
        self._engine_raised: _Raised | None = None
        self._on_error: OnError | None = None
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
                name=p.name, data_type_ref=p.data_type_ref.code, value=p.default_value or ""
            )
            for p in profile.parameter_profiles
        }
        resources = list(component.rois_resources())
        self._hosted[ref] = _Hosted(
            name,
            ref,
            component,
            profile,
            parameters,
            resources,
            rois_common=ROIS_COMMON_URN in profile.sub_component_profiles,
        )
        component.rois_bind(_Binding(self, ref))
        for resource in resources:
            if not any(known is resource for known in self._resources):
                self._resources.append(resource)
                resource.rois_bind(_ResourceBinding(self, resource))
        return ref

    def hosted(self, ref: str) -> _Hosted:
        """The hosted component of a ref."""
        return self._hosted[ref]

    def components(self) -> list[LocalComponent]:
        """Every hosted component, in the order they were added."""
        return [hosted.component for hosted in self._hosted.values()]

    async def start(self) -> None:
        """Open the resources and connect every component, in the order they were added.

        A resource opens before the first component that uses it connects. A component
        whose resource or connect() fails reports ERROR, and one whose resource failed
        is never connected.
        """
        self._loop = asyncio.get_running_loop()
        failed: list[LocalResource] = []
        for hosted in self._hosted.values():
            usable = True
            for resource in hosted.resources:
                if any(r is resource for r in failed):
                    usable = False
                    continue
                if any(r is resource for r in self._opened):
                    continue
                try:
                    await resource.open()
                except Exception:
                    logger.exception("A resource of %s could not open", hosted.ref)
                    failed.append(resource)
                    usable = False
                else:
                    self._opened.append(resource)
            if not usable:
                hosted.state = _State.FAILED
                continue
            try:
                await hosted.component.connect()
            except Exception:
                logger.exception("%s could not connect to its backend", hosted.ref)
                hosted.state = _State.FAILED
            else:
                hosted.state = _State.READY

    async def stop(self) -> None:
        """Cancel every running command, disconnect every component, close the resources.

        The resources close after every component has disconnected, in the reverse
        order of opening, so a component leaves a shared backend while it still runs.
        """
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
            hosted.started = False
            self._lift(hosted, aborted=True)
        for resource in reversed(self._opened):
            try:
                await resource.close()
            except Exception:
                logger.exception("A resource could not close")
        self._opened.clear()
        self._subscriptions.clear()

    def status(self, ref: str) -> ComponentStatus:
        """The status of a component, before the engine applies its binds.

        ERROR, raised or from a failed start, comes above WARNING, which comes above the
        lifecycle: UNINITIALIZED until the resources are open and the component has
        connected, then READY.
        """
        hosted = self._hosted[ref]
        raised = _strongest(hosted.raised.values())
        if hosted.state is _State.FAILED or raised is ComponentStatus.ERROR:
            return ComponentStatus.ERROR
        if raised is ComponentStatus.WARNING:
            return ComponentStatus.WARNING
        if hosted.state is _State.UNINITIALIZED:
            return ComponentStatus.UNINITIALIZED
        return ComponentStatus.READY

    def engine_status(self) -> ComponentStatus:
        """The status of the engine: ERROR or WARNING as raised on it, or READY."""
        raised = self._engine_raised
        return raised.status if raised is not None else ComponentStatus.READY

    # -- The component contract ----------------------------------------------------------

    @property
    def engine_ids(self) -> frozenset[str]:
        return frozenset({self._engine_id})

    def profiles(self) -> Mapping[str, HRIComponentProfile]:
        return {ref: hosted.profile for ref, hosted in self._hosted.items()}

    def engine_profile(self) -> HRIEngineProfileType | None:
        return None

    def on_error(self, callback: OnError) -> None:
        self._on_error = callback

    def keep_running(self, command_id: str) -> None:
        # A local command belongs to the client that started it, so an abort always
        # halts it. The engine asks only child engines to keep commands running.
        return

    async def run(self, unit: CommandUnit) -> CompletedStatus:
        received = asyncio.get_running_loop().time()
        hosted = self._hosted[unit.component_ref]
        if unit.command_type == "set_parameter":
            parameters = [_parameter(hosted, a.name, a.value) for a in unit.arguments]
            applied = await self._apply(hosted, parameters)
            self._keep(unit.command_id, [])
            # Inside an execute the command already runs, so a refusal ends it with ERROR.
            return CompletedStatus.ERROR if applied is _REFUSED else applied
        if not self._operable(hosted):
            self._keep(unit.command_id, [])
            return CompletedStatus.ERROR
        if hosted.rois_common:
            # A start a stop cancelled may still be unwinding. It still runs, so a
            # second stop cancels it again rather than doing nothing.
            unwinding = unit.command_type == "stop" and hosted.start is not None
            if unit.command_type in _UNSTARTED_NO_OPS and not hosted.started and not unwinding:
                self._keep(unit.command_id, [])
                return CompletedStatus.OK
            if unit.command_type == "suspend":
                return await self._suspend(hosted, unit)
            if unit.command_type == "resume":
                return await self._resume(hosted, unit)
            if unit.command_type != "stop":
                held = await self._held(hosted, unit, received)
                if held is None and not self._operable(hosted):
                    held = CompletedStatus.ERROR
                if held is not None:
                    self._keep(unit.command_id, [])
                    return held
        if unit.command_type == "start":
            return await self._start(hosted, unit, received)
        if unit.command_type == "stop":
            return await self._stop(hosted, unit)
        return await self._end(hosted, unit, self._begin(hosted, unit))

    async def set_parameter(
        self, ref: str, parameters: Sequence[Parameter]
    ) -> tuple[SetParameterResult, CompletedStatus]:
        hosted = self._hosted[ref]
        status = await self._apply(hosted, parameters)
        if status is _REFUSED:
            # The component's hook refused the values: the request is answered
            # BAD_PARAMETER (Table 8.1) and no command runs.
            return SetParameterResult(return_code=ReturnCode.BAD_PARAMETER), CompletedStatus.ERROR
        command_id = self._new_id("param")
        self._keep(command_id, [])
        return SetParameterResult(return_code=ReturnCode.OK, command_id=command_id), status

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

    async def query(self, ref: str, query_type: str, arguments: Sequence[Argument]) -> QueryResult:
        hosted = self._hosted[ref]
        if query_type == _STATUS_QUERY:
            status = Result(name="status", data_type_ref="Component_Status", value=self.status(ref))
            return QueryResult(return_code=ReturnCode.OK, results=[status])
        if not self._operable(hosted):
            return QueryResult(return_code=ReturnCode.ERROR)
        try:
            results = await hosted.component.rois_query(query_type, arguments)
        except Exception:
            logger.exception("%s failed to answer %s", ref, query_type)
            return QueryResult(return_code=ReturnCode.ERROR)
        return QueryResult(return_code=ReturnCode.OK, results=results)

    async def subscribe(
        self, ref: str, event_type: str, arguments: Sequence[Argument], deliver: Deliver
    ) -> SubscribeResult:
        hosted = self._hosted[ref]
        if not self._operable(hosted):
            return SubscribeResult(return_code=ReturnCode.ERROR)
        try:
            await hosted.component.rois_subscribed(event_type, arguments)
        except Exception:
            logger.exception("%s failed to start the subscription to %s", ref, event_type)
            return SubscribeResult(return_code=ReturnCode.ERROR)
        # The subscription takes events from here on, so its first event cannot reach
        # the client before the reply that names it.
        subscribe_id = self._new_id("sub")
        self._subscriptions[subscribe_id] = _Subscription(
            ref, event_type, {a.name: a.value for a in arguments}, deliver
        )
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
        error = self._errors.get(error_id)
        if error is None:
            return GetErrorDetailResult(return_code=ReturnCode.BAD_PARAMETER)
        return GetErrorDetailResult(
            return_code=ReturnCode.OK,
            results=[
                Result(name="component_ref", data_type_ref="RoISIdentifier", value=error.ref),
                Result(name="status", data_type_ref="Component_Status", value=error.status),
                Result(name="message", data_type_ref="string", value=error.message),
                Result(name="time", data_type_ref="DateTime", value=error.time.isoformat()),
            ],
        )

    # -- Statuses and errors -------------------------------------------------------------

    def call(self, function: Callable[..., None], *args: Any) -> None:
        """Run a function on the event loop of the engine, from any thread.

        Before the engine starts, and on the loop itself, it runs at once.
        """
        loop = self._loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if loop is None or running is loop:
            function(*args)
            return
        try:
            loop.call_soon_threadsafe(function, *args)
        except RuntimeError:
            logger.warning("A status changed after the engine stopped. Dropped.")

    def raise_component_status(
        self, ref: str, key: object, status: ComponentStatus, message: str
    ) -> None:
        """Record a status the component raised, and report an error if it changed."""
        self._raise(self._hosted[ref], key, status, message, ErrorType.COMPONENT_INTERNAL_ERROR)

    def clear_component_status(self, ref: str, key: object) -> None:
        """Withdraw the status the component raised."""
        self._clear(self._hosted[ref], key)

    def raise_resource_status(
        self, resource: LocalResource, status: ComponentStatus, message: str
    ) -> None:
        """Record a status a resource raised on every component that uses it."""
        for hosted in self._users_of(resource):
            self._raise(hosted, resource, status, message, ErrorType.COMPONENT_NOT_RESPONDING)

    def clear_resource_status(self, resource: LocalResource) -> None:
        """Withdraw the status a resource raised from every component that uses it."""
        for hosted in self._users_of(resource):
            self._clear(hosted, resource)

    def raise_engine_status(self, status: ComponentStatus, message: str) -> None:
        """Record a status raised on the engine itself. Safe to call from any thread.

        Raises:
            ValueError: The status is neither WARNING nor ERROR.
        """
        _check_raisable(status)
        self.call(self._raise_engine, status, message)

    def clear_engine_status(self) -> None:
        """Withdraw the status raised on the engine. Safe to call from any thread."""
        self.call(self._clear_engine)

    def _raise(
        self,
        hosted: _Hosted,
        key: object,
        status: ComponentStatus,
        message: str,
        error_type: ErrorType,
    ) -> None:
        # Each raise that changes what the component reports is an error. A raise that
        # changes nothing keeps the errors the source raised before.
        before = self.status(hosted.ref)
        previous = hosted.raised.get(key)
        hosted.raised[key] = _Raised(status, message, previous.errors if previous else ())
        if self.status(hosted.ref) is before:
            return
        error_id = self._new_id("err")
        self._errors[error_id] = _Error(hosted.ref, status, message, datetime.now(UTC))
        hosted.raised[key] = _Raised(status, message, (*hosted.raised[key].errors, error_id))
        if self._on_error is not None:
            self._on_error(hosted.ref, error_id, error_type)

    def _clear(self, hosted: _Hosted, key: object) -> None:
        # A cleared status sends nothing, since RoIS has no message for it. Clients see
        # component_status return to what the component reports without it.
        raised = hosted.raised.pop(key, None)
        if raised is not None:
            for error_id in raised.errors:
                self._errors.pop(error_id, None)

    def _raise_engine(self, status: ComponentStatus, message: str) -> None:
        previous = self._engine_raised
        if previous is not None and previous.status is status:
            self._engine_raised = _Raised(status, message, previous.errors)
            return
        error_id = self._new_id("err")
        self._errors[error_id] = _Error("", status, message, datetime.now(UTC))
        self._engine_raised = _Raised(
            status, message, (*(previous.errors if previous else ()), error_id)
        )
        if self._on_error is not None:
            self._on_error("", error_id, ErrorType.ENGINE_INTERNAL_ERROR)

    def _clear_engine(self) -> None:
        raised, self._engine_raised = self._engine_raised, None
        if raised is not None:
            for error_id in raised.errors:
                self._errors.pop(error_id, None)

    def _users_of(self, resource: LocalResource) -> list[_Hosted]:
        return [h for h in self._hosted.values() if any(r is resource for r in h.resources)]

    def _operable(self, hosted: _Hosted) -> bool:
        """Whether a component takes commands and queries: started, no ERROR raised."""
        return (
            hosted.state is _State.READY
            and _strongest(hosted.raised.values()) is not ComponentStatus.ERROR
        )

    # -- Events --------------------------------------------------------------------------

    def emit(
        self,
        ref: str,
        event_type: str,
        results: list[Result],
        concerning: Mapping[str, str] | None = None,
    ) -> None:
        """Publish an event of a component, from any thread."""
        if self._loop is None:
            logger.warning("%s emitted %s before the engine started. Dropped.", ref, event_type)
            return
        self.call(self._publish, ref, event_type, results, dict(concerning or {}))

    def _publish(
        self, ref: str, event_type: str, results: list[Result], concerning: Mapping[str, str]
    ) -> None:
        """Send one event to its subscriptions and keep it for get_event_detail.

        A component in ERROR holds back its events, and so does a suspended one. Its
        subscriptions stay, and its events flow again once the status clears or the
        component resumes. Events held back are dropped, not replayed.
        """
        hosted = self._hosted[ref]
        if not self._operable(hosted) or hosted.suspension is not None:
            return
        subscriptions = [
            (subscribe_id, s)
            for subscribe_id, s in self._subscriptions.items()
            if s.ref == ref and s.event_type == event_type and _concerns(s, concerning)
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
        """Wait until a command ends and keep its results.

        A command runs for as long as its handler does. Its timeout judges only whether
        it started (Table 8.21), which a handler that runs has.
        """
        results: list[Result] = []
        status: CompletedStatus | None = None
        try:
            try:
                results = await task
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    # The engine aborts the command, which also cancelled the handler.
                    # A start leaves its backend moving, so the stop handler halts it.
                    if unit.command_type == "start":
                        halt = asyncio.ensure_future(self._halt_backend(hosted))
                        try:
                            await asyncio.shield(halt)
                        except asyncio.CancelledError:
                            pass
                    self._keep(unit.command_id, [])
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
            # A start that ends other than OK ends started, unless a newer start began.
            if (
                unit.command_type == "start"
                and status is not CompletedStatus.OK
                and hosted.start is None
            ):
                hosted.started = False
        self._keep(unit.command_id, results if status is CompletedStatus.OK else [])
        return status

    async def _start(self, hosted: _Hosted, unit: CommandUnit, received: float) -> CompletedStatus:
        """Run a start, after the start before it ended with ABORT.

        The start must begin within the timeout of its profile, counted from its
        receipt, or it ends with TIMEOUT without running.
        """
        # The new start replaces the latest one at once, so a stop or a later start that
        # arrives while this one waits for its turn aborts this one.
        previous = hosted.start
        current = _Start(unit.command_id)
        hosted.start = current
        # The component counts as started from here, so a stop that arrives while this
        # start waits for its turn aborts it.
        hosted.started = True
        if previous is not None:
            hosted.aborted.add(previous.command_id)
        timeout = _timeout(hosted, unit.command_type)
        remaining = None
        if timeout is not None:
            remaining = max(0.0, received + timeout - asyncio.get_running_loop().time())
        taking_over = asyncio.ensure_future(self._take_over(hosted, previous))
        try:
            await asyncio.wait_for(asyncio.shield(taking_over), remaining)
        except (TimeoutError, asyncio.CancelledError) as exc:
            # The start before this one still unwinds, and the lock passes on once it has.
            taking_over.add_done_callback(partial(_release_after, hosted.takeover))
            hosted.aborted.discard(unit.command_id)
            if hosted.start is current:
                hosted.start = None
                hosted.started = False
            self._keep(unit.command_id, [])
            if isinstance(exc, asyncio.CancelledError):
                raise
            return CompletedStatus.TIMEOUT
        try:
            if unit.command_id in hosted.aborted:
                self._keep(unit.command_id, [])
                return CompletedStatus.ABORT
            current.task = self._begin(hosted, unit)
        finally:
            hosted.takeover.release()
            if current.task is None:
                hosted.aborted.discard(unit.command_id)
                if hosted.start is current:
                    hosted.start = None
                    hosted.started = False
        return await self._end(hosted, unit, current.task)

    async def _take_over(self, hosted: _Hosted, previous: _Start | None) -> None:
        """Take the turn of the starts and halt the start before, keeping the lock."""
        await hosted.takeover.acquire()
        try:
            if previous is not None and previous.task is not None:
                await self._halt(hosted, previous.task)
        except BaseException:
            hosted.takeover.release()
            raise

    async def _stop(self, hosted: _Hosted, unit: CommandUnit) -> CompletedStatus:
        """End the suspension, run the stop handler at once, then cancel the latest start."""
        hosted.started = False
        self._lift(hosted, aborted=True)
        current = hosted.start
        if current is not None:
            # The start ends with ABORT even if halting the backend ends it first.
            hosted.aborted.add(current.command_id)
        status = await self._end(hosted, unit, self._begin(hosted, unit))
        if current is not None and current.task is not None:
            current.task.cancel()
        return status

    async def _suspend(self, hosted: _Hosted, unit: CommandUnit) -> CompletedStatus:
        """Hold the component's commands, then run the suspend handler.

        A suspend that fails lifts the hold it put in force, since the component is not
        suspended when the command says so.
        """
        suspension = hosted.suspension
        if suspension is None:
            suspension = hosted.suspension = _Suspension()
            fresh = True
        else:
            fresh = False
        status = await self._end(hosted, unit, self._begin(hosted, unit))
        if status is not CompletedStatus.OK and fresh and hosted.suspension is suspension:
            self._lift(hosted, aborted=False)
        return status

    async def _resume(self, hosted: _Hosted, unit: CommandUnit) -> CompletedStatus:
        """Run the resume handler, then release the commands held, if it succeeded."""
        status = await self._end(hosted, unit, self._begin(hosted, unit))
        if status is CompletedStatus.OK:
            self._lift(hosted, aborted=False)
        return status

    async def _held(
        self, hosted: _Hosted, unit: CommandUnit, received: float
    ) -> CompletedStatus | None:
        """Wait while the component is suspended. None once released, else the end status.

        The command never started, so its profile timeout, counted from its receipt,
        ends it with TIMEOUT, and a stop ends it with ABORT.
        """
        timeout = _timeout(hosted, unit.command_type)
        loop = asyncio.get_running_loop()
        while (suspension := hosted.suspension) is not None:
            remaining = None if timeout is None else received + timeout - loop.time()
            try:
                await asyncio.wait_for(suspension.released.wait(), remaining)
            except TimeoutError:
                return CompletedStatus.TIMEOUT
            if suspension.aborted:
                return CompletedStatus.ABORT
        return None

    def _lift(self, hosted: _Hosted, *, aborted: bool) -> None:
        """End the suspension in force, releasing or aborting the commands it held."""
        suspension, hosted.suspension = hosted.suspension, None
        if suspension is not None:
            suspension.aborted = aborted
            suspension.released.set()

    async def _halt(self, hosted: _Hosted, task: asyncio.Task[list[Result]]) -> None:
        """Run the stop handler, within its timeout, then cancel a start and wait for it."""
        if not task.done():
            await self._halt_backend(hosted)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _halt_backend(self, hosted: _Hosted) -> None:
        """Run the stop handler of a component, if it has one, within its timeout."""
        if not any(m.name == "stop" for m in hosted.profile.command_profiles):
            return
        try:
            async with asyncio.timeout(_timeout(hosted, "stop")):
                await hosted.component.rois_command("stop", [])
        except Exception:
            logger.exception("%s failed to stop", hosted.ref)

    async def _apply(
        self, hosted: _Hosted, parameters: Sequence[Parameter]
    ) -> CompletedStatus | _Refused:
        """Run the parameter hook and store the new values if it accepts them.

        _REFUSED when the hook refused them, and the old values stay.
        """
        if not self._operable(hosted):
            return CompletedStatus.ERROR
        try:
            await hosted.component.rois_set_parameters(parameters)
        except Exception as exc:
            logger.warning("%s refused new parameter values: %s", hosted.ref, exc)
            return _REFUSED
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


def _check_raisable(status: ComponentStatus) -> None:
    if status not in _RAISABLE:
        raise ValueError(f"Only WARNING or ERROR can be raised, not {status.value}")


def _strongest(raised: Any) -> ComponentStatus | None:
    """The strongest of the raised statuses: ERROR, then WARNING, or None."""
    statuses = {r.status for r in raised}
    if ComponentStatus.ERROR in statuses:
        return ComponentStatus.ERROR
    if ComponentStatus.WARNING in statuses:
        return ComponentStatus.WARNING
    return None


def _concerns(subscription: _Subscription, concerning: Mapping[str, str]) -> bool:
    """Whether an event reaches a subscription.

    The argument values the event concerns must equal those the subscription gave. An
    argument the subscription did not give matches any value, and an event that names
    no values reaches every subscription.
    """
    return all(
        subscription.arguments.get(name, value) == value for name, value in concerning.items()
    )


def _release_after(lock: asyncio.Lock, taking_over: asyncio.Future[None]) -> None:
    """Pass the turn of the starts on once a takeover nobody waits for any more is done.

    A takeover that failed released the lock itself.
    """
    if not taking_over.cancelled() and taking_over.exception() is None:
        lock.release()


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
