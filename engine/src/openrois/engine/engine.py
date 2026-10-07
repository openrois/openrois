"""The recursive RoIS HRI Engine.

``Engine`` answers the RoIS method catalog for the sessions connected to it: clients of
a gateway, or the parent engine of an adapter. It reaches its components through the
component contract (``openrois.engine.contract``): the components it hosts in its own
process, and the components of its child engines. One class serves an adapter (local
components), a gateway (child engines) and a middle tier (both).

The engine does what is the same for every component:

- It selects components by condition, in the OpenRoIS subset of CQL2-Text.
- It holds the bindings of actuation components for the sessions connected to it.
  Requests from a parent engine skip the check, since the parent made it.
- It runs ``execute``: the items in order, each ``delay_time`` waited, the commands of
  a ``ConcurrentCommands`` item at the same time, each after its own ``delay_time``. A
  command that ends other than OK stops the sequence, and the commands after it
  complete with ABORT.
- It keeps the command table, refuses a command id it already tracks or one in the
  namespace of an engine, and sends every ``rois.command.completed`` once, to the
  session that started the command.
- It routes subscriptions, results, events and errors to the source that owns them.

Clients connect to the top engine of a hierarchy, which holds the bindings for every
engine below it. A middle tier serves its parent through a trusted session, so it does
not check the bindings of its parent's clients against those of its own clients.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from dataclasses import dataclass
from typing import Any

from openrois.interfaces.catalog import (
    BindAnyParams,
    BindAnyResult,
    BindParams,
    BindResult,
    ConnectParams,
    ConnectResult,
    DisconnectParams,
    DisconnectResult,
    ExecuteParams,
    ExecuteResult,
    GetCommandResultParams,
    GetCommandResultResult,
    GetErrorDetailParams,
    GetErrorDetailResult,
    GetEventDetailParams,
    GetEventDetailResult,
    GetParameterParams,
    GetParameterResult,
    GetProfileParams,
    GetProfileResult,
    QueryParams,
    QueryResult,
    ReleaseParams,
    ReleaseResult,
    SearchParams,
    SearchResult,
    SetParameterParams,
    SetParameterResult,
    SubscribeParams,
    SubscribeResult,
    UnsubscribeParams,
    UnsubscribeResult,
)
from openrois.interfaces.condition import (
    COMPONENT_REF,
    COMPONENT_TYPE,
    ConditionError,
    component_type_urn,
    parse_condition,
)
from openrois.interfaces.hri import (
    CommandUnit,
    CommandUnitSequenceItem,
    Parameter,
    ReturnCode,
)
from openrois.interfaces.profiles import (
    ComponentFunction,
    HRIComponentProfile,
    HRIEngineProfileType,
    RoISIdentifierType,
)
from openrois.interfaces.service import (
    CompletedParams,
    CompletedStatus,
    NotifyEventParams,
    ProfileChangedParams,
)
from openrois.interfaces.values import decode_value
from pydantic import BaseModel

from openrois.engine.contract import ComponentContract, Deliver
from openrois.engine.local import LocalComponent, LocalComponents
from openrois.engine.session import Notify, Session

logger = logging.getLogger(__name__)

# How many finished commands the table keeps, for get_command_result and duplicate ids.
_COMMANDS_KEPT = 4096

#: The authority of the engine profile identifier.
ENGINE_AUTHORITY = "OpenRoIS"

type _Handler = Callable[[Session, Any], Awaitable[BaseModel]]


@dataclass(eq=False)
class _Command:
    """An entry of the command table.

    ``source`` ran the command and keeps its results. It is None for a command that
    never ran, which has no results.
    """

    session_id: str
    source: ComponentContract | None = None
    status: CompletedStatus | None = None


@dataclass(frozen=True, slots=True)
class _Subscription:
    session_id: str
    source: ComponentContract


class Engine:
    """The recursive RoIS HRI Engine.

    Typical use in an adapter::

        engine = Engine("robot_1")
        engine.add_component("navigation", Navigation(config))
        await WsClient(engine, "ws://gateway:8765").run_async()

    and in a gateway, where WsServer adds each child engine that connects::

        engine = Engine("gateway")
        server = WsServer(engine)
        await engine.start()
        await server.start()
    """

    def __init__(self, engine_id: str, *, event_lifetime: float = 60.0) -> None:
        """Initialize an engine with no components.

        Args:
            engine_id: The id of this engine. Every ref of a local component is
                ``engine_id/name``, so the id must be unique across the deployment.
            event_lifetime: Seconds that get_event_detail keeps an event of a local
                component after its notification.

        Raises:
            ValueError: The engine id is empty or contains a slash.
        """
        if not engine_id or "/" in engine_id:
            raise ValueError(f"An engine id must be non-empty and free of slashes: {engine_id!r}")
        self._engine_id = engine_id
        self._local = LocalComponents(engine_id, event_lifetime=event_lifetime)
        self._children: list[ComponentContract] = []
        self._sessions: dict[str, Session] = {}
        self._bindings: dict[str, str] = {}
        self._commands: dict[str, _Command] = {}
        self._subscriptions: dict[str, _Subscription] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._next_session = 0
        self._handlers: dict[str, _Handler] = {
            "rois.system.connect": self._connect,
            "rois.system.disconnect": self._disconnect,
            "rois.system.get_profile": self._get_profile,
            "rois.system.get_error_detail": self._get_error_detail,
            "rois.command.search": self._search,
            "rois.command.bind": self._bind_request,
            "rois.command.bind_any": self._bind_any,
            "rois.command.release": self._release,
            "rois.command.get_parameter": self._get_parameter,
            "rois.command.set_parameter": self._set_parameter,
            "rois.command.execute": self._execute,
            "rois.command.get_command_result": self._get_command_result,
            "rois.query.query": self._query,
            "rois.event.subscribe": self._subscribe,
            "rois.event.unsubscribe": self._unsubscribe,
            "rois.event.get_event_detail": self._get_event_detail,
        }

    @property
    def engine_id(self) -> str:
        """The id of this engine."""
        return self._engine_id

    # -- Components and child engines ----------------------------------------------------

    def add_component(self, name: str, component: LocalComponent) -> str:
        """Host a component in this process, and return its ref, ``engine_id/name``.

        Add components before :meth:`start`.

        Raises:
            ValueError: The name is empty, contains a slash, or is taken.
        """
        return self._local.add(name, component)

    def local_components(self) -> list[LocalComponent]:
        """The components this engine hosts in its process."""
        return self._local.components()

    def add_child(self, child: ComponentContract) -> None:
        """Add a discovered child engine and tell every session that the profile changed.

        Raises:
            ValueError: An engine id of the child is already in the tree.
        """
        self.check_engine_ids(child, child.engine_ids)
        self._children.append(child)
        self.profile_changed()

    def check_engine_ids(self, child: ComponentContract, engine_ids: frozenset[str]) -> None:
        """Refuse engine ids for a child that this engine or another child already uses.

        Raises:
            ValueError: One of the engine ids is taken.
        """
        taken = set(self._local.engine_ids)
        for other in self._children:
            if other is not child:
                taken |= other.engine_ids
        clash = sorted(engine_ids & taken)
        if clash:
            raise ValueError(f"Engine id {clash[0]} is already in use.")

    def remove_child(self, child: ComponentContract) -> None:
        """Remove a child engine whose connection is gone, with its bindings."""
        if child not in self._children:
            return
        refs = set(child.profiles())
        self._children.remove(child)
        for ref in refs & set(self._bindings):
            del self._bindings[ref]
        gone = [s for s, entry in self._subscriptions.items() if entry.source is child]
        for subscribe_id in gone:
            del self._subscriptions[subscribe_id]
        self.profile_changed()

    def child_engine_ids(self) -> list[str]:
        """The ids of the connected child engines, in the order they connected."""
        return [p.identifier.code for c in self._children if (p := c.engine_profile()) is not None]

    async def start(self) -> None:
        """Connect the local components to their backends."""
        await self._local.start()

    async def stop(self) -> None:
        """Cancel every running sequence and disconnect the local components."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._local.stop()

    # -- Sessions ------------------------------------------------------------------------

    def open_session(self, notify: Notify, *, trusted: bool = False) -> Session:
        """Open a session for a client, or with ``trusted`` for the parent engine."""
        self._next_session += 1
        session = Session(f"session-{self._next_session}", notify, trusted)
        self._sessions[session.id] = session
        return session

    async def close_session(self, session: Session) -> None:
        """Release what a session held: its bindings and its subscriptions."""
        await self._release_session(session)
        self._sessions.pop(session.id, None)

    def profile_changed(self) -> None:
        """Tell every session that the engine profile changed."""
        for session in list(self._sessions.values()):
            session.notify("rois.system.profile_changed", ProfileChangedParams())

    async def handle(self, session: Session, method: str, params: BaseModel) -> BaseModel:
        """Answer one catalog request of a session with its result model.

        Args:
            session: The session that sent the request.
            method: A method of the catalog, for example ``rois.command.execute``.
            params: The params, already validated against the catalog model.

        Raises:
            KeyError: The method is not in the catalog.
        """
        return await self._handlers[method](session, params)

    # -- SystemIF ------------------------------------------------------------------------

    async def _connect(self, session: Session, params: ConnectParams) -> ConnectResult:
        return ConnectResult(return_code=ReturnCode.OK)

    async def _disconnect(self, session: Session, params: DisconnectParams) -> DisconnectResult:
        await self._release_session(session)
        return DisconnectResult(return_code=ReturnCode.OK)

    async def _get_profile(self, session: Session, params: GetProfileParams) -> GetProfileResult:
        selected = self._select(params.condition)
        if selected is None:
            return GetProfileResult(return_code=ReturnCode.BAD_PARAMETER)
        components = self._components()
        chosen = set(selected)
        sub_profiles: list[HRIEngineProfileType] = []
        for child in self._children:
            profile = child.engine_profile()
            if profile is None:
                continue
            if params.condition.strip():
                trimmed = _trim(profile, chosen)
                if trimmed is not None:
                    sub_profiles.append(trimmed)
            else:
                sub_profiles.append(profile)
        return GetProfileResult(
            return_code=ReturnCode.OK,
            profile=HRIEngineProfileType(
                identifier=RoISIdentifierType(authority=ENGINE_AUTHORITY, code=self._engine_id),
                sub_profiles=sub_profiles,
                component_ids=selected,
            ),
            component_profiles={ref: components[ref][0] for ref in selected},
        )

    async def _get_error_detail(
        self, session: Session, params: GetErrorDetailParams
    ) -> GetErrorDetailResult:
        source = self._owner_of(params.error_id)
        if not _empty_filter(params.condition) or source is None:
            return GetErrorDetailResult(return_code=ReturnCode.BAD_PARAMETER)
        return await source.error_detail(params.error_id)

    # -- CommandIF -----------------------------------------------------------------------

    async def _search(self, session: Session, params: SearchParams) -> SearchResult:
        selected = self._select(params.condition)
        if selected is None:
            return SearchResult(return_code=ReturnCode.BAD_PARAMETER)
        return SearchResult(return_code=ReturnCode.OK, component_ref_list=selected)

    async def _bind_request(self, session: Session, params: BindParams) -> BindResult:
        profile = self._profile(params.component_ref)
        if profile is None:
            return BindResult(return_code=ReturnCode.UNSUPPORTED)
        return BindResult(return_code=self._bind(session, params.component_ref, profile))

    async def _bind_any(self, session: Session, params: BindAnyParams) -> BindAnyResult:
        selected = self._select(params.condition)
        if selected is None:
            return BindAnyResult(return_code=ReturnCode.BAD_PARAMETER)
        if not selected:
            return BindAnyResult(return_code=ReturnCode.UNSUPPORTED)
        components = self._components()
        for ref in selected:
            if self._bind(session, ref, components[ref][0]) is ReturnCode.OK:
                return BindAnyResult(return_code=ReturnCode.OK, component_ref=ref)
        return BindAnyResult(return_code=ReturnCode.OUT_OF_RESOURCES)

    async def _release(self, session: Session, params: ReleaseParams) -> ReleaseResult:
        if self._profile(params.component_ref) is None:
            return ReleaseResult(return_code=ReturnCode.UNSUPPORTED)
        if self._bindings.get(params.component_ref) == session.id:
            del self._bindings[params.component_ref]
        return ReleaseResult(return_code=ReturnCode.OK)

    async def _get_parameter(
        self, session: Session, params: GetParameterParams
    ) -> GetParameterResult:
        entry = self._components().get(params.component_ref)
        if entry is None:
            return GetParameterResult(return_code=ReturnCode.UNSUPPORTED)
        return await entry[1].get_parameter(params.component_ref)

    async def _set_parameter(
        self, session: Session, params: SetParameterParams
    ) -> SetParameterResult:
        entry = self._components().get(params.component_ref)
        if entry is None:
            return SetParameterResult(return_code=ReturnCode.UNSUPPORTED)
        profile, source = entry
        if not self._holds(session, params.component_ref, profile):
            return SetParameterResult(return_code=ReturnCode.OUT_OF_RESOURCES)
        parameters = _checked_parameters(profile, params.parameters)
        if parameters is None:
            return SetParameterResult(return_code=ReturnCode.BAD_PARAMETER)

        command = _Command(session.id, source)

        def completed(command_id: str, status: CompletedStatus) -> None:
            self._complete(session, command_id, command, status)

        result = await source.set_parameter(params.component_ref, parameters, completed)
        if result.return_code is ReturnCode.OK and result.command_id:
            known = self._commands.get(result.command_id)
            if known is None or known.status is not None:
                # The entry replaces a finished command of the same id, which an engine
                # below assigns again after it restarted.
                self._commands[result.command_id] = command
                self._prune_commands()
            else:
                logger.warning(
                    "Command id %s of a set_parameter is taken by a running command.",
                    result.command_id,
                )
        return result

    async def _execute(self, session: Session, params: ExecuteParams) -> ExecuteResult:
        units = [unit for item in params.command_unit_list for unit in _units(item)]
        if not units:
            return ExecuteResult(return_code=ReturnCode.BAD_PARAMETER)
        components = self._components()
        seen: set[str] = set()
        for unit in units:
            entry = components.get(unit.component_ref)
            if entry is None or not _declares(entry[0], unit.command_type):
                return ExecuteResult(return_code=ReturnCode.UNSUPPORTED)
            if not self._holds(session, unit.component_ref, entry[0]):
                return ExecuteResult(return_code=ReturnCode.OUT_OF_RESOURCES)
            if not _checked_arguments(entry[0], unit):
                return ExecuteResult(return_code=ReturnCode.BAD_PARAMETER)
            if (
                not unit.command_id
                or unit.command_id in self._commands
                or unit.command_id in seen
                or self._owner_of(unit.command_id) is not None
            ):
                return ExecuteResult(return_code=ReturnCode.BAD_PARAMETER)
            seen.add(unit.command_id)
        for unit in units:
            source = components[unit.component_ref][1]
            self._commands[unit.command_id] = _Command(session.id, source)
        self._prune_commands()
        self._spawn(self._run_sequence(session, params.command_unit_list))
        return ExecuteResult(return_code=ReturnCode.OK)

    async def _get_command_result(
        self, session: Session, params: GetCommandResultParams
    ) -> GetCommandResultResult:
        command = self._commands.get(params.command_id)
        if not _empty_filter(params.condition) or command is None:
            return GetCommandResultResult(return_code=ReturnCode.BAD_PARAMETER)
        if command.source is None:
            # The command never ran, because its sequence stopped before it.
            return GetCommandResultResult(return_code=ReturnCode.OK)
        return await command.source.command_result(params.command_id)

    # -- QueryIF and EventIF -------------------------------------------------------------

    async def _query(self, session: Session, params: QueryParams) -> QueryResult:
        picked = self._pick(
            params.condition, lambda p: any(q.name == params.query_type for q in p.query_profiles)
        )
        if isinstance(picked, ReturnCode):
            return QueryResult(return_code=picked)
        ref, source = picked
        return await source.query(ref, params.query_type)

    async def _subscribe(self, session: Session, params: SubscribeParams) -> SubscribeResult:
        picked = self._pick(
            params.condition, lambda p: any(e.name == params.event_type for e in p.event_profiles)
        )
        if isinstance(picked, ReturnCode):
            return SubscribeResult(return_code=picked)
        ref, source = picked
        result = await source.subscribe(ref, params.event_type, self._deliverer(session))
        if result.return_code is ReturnCode.OK:
            self._subscriptions[result.subscribe_id] = _Subscription(session.id, source)
        return result

    async def _unsubscribe(self, session: Session, params: UnsubscribeParams) -> UnsubscribeResult:
        subscription = self._subscriptions.get(params.subscribe_id)
        if subscription is not None and subscription.session_id == session.id:
            del self._subscriptions[params.subscribe_id]
            await subscription.source.unsubscribe(params.subscribe_id)
        return UnsubscribeResult(return_code=ReturnCode.OK)

    async def _get_event_detail(
        self, session: Session, params: GetEventDetailParams
    ) -> GetEventDetailResult:
        source = self._owner_of(params.event_id)
        if not _empty_filter(params.condition) or source is None:
            return GetEventDetailResult(return_code=ReturnCode.BAD_PARAMETER)
        return await source.event_detail(params.event_id)

    # -- Commands ------------------------------------------------------------------------

    async def _run_sequence(
        self, session: Session, items: Sequence[CommandUnitSequenceItem]
    ) -> None:
        """Run the items of an execute in order, the commands of one item together."""
        for index, item in enumerate(items):
            if item.delay_time:
                await asyncio.sleep(item.delay_time / 1000)
            if isinstance(item, CommandUnit):
                statuses = [await self._run_unit(session, item)]
            else:
                statuses = await asyncio.gather(
                    *(self._run_unit(session, unit, delayed=True) for unit in item.command_list)
                )
            if any(status is not CompletedStatus.OK for status in statuses):
                for later in items[index + 1 :]:
                    for unit in _units(later):
                        self._commands[unit.command_id].source = None
                        self._finish(session, unit.command_id, CompletedStatus.ABORT)
                return

    async def _run_unit(
        self, session: Session, unit: CommandUnit, *, delayed: bool = False
    ) -> CompletedStatus:
        """Run one command and finish it. ``delayed`` waits its own delay_time first."""
        if delayed and unit.delay_time:
            await asyncio.sleep(unit.delay_time / 1000)
        entry = self._components().get(unit.component_ref)
        if entry is None:
            status = CompletedStatus.ERROR
        else:
            try:
                status = await entry[1].run(unit)
            except Exception:
                logger.exception("Command %s failed", unit.command_id)
                status = CompletedStatus.ERROR
        self._finish(session, unit.command_id, status)
        return status

    def _finish(self, session: Session, command_id: str, status: CompletedStatus) -> None:
        """Record how a command of an execute ended."""
        command = self._commands.setdefault(command_id, _Command(session.id))
        self._complete(session, command_id, command, status)

    def _complete(
        self, session: Session, command_id: str, command: _Command, status: CompletedStatus
    ) -> None:
        """Record how a command ended and tell the session that started it, once."""
        if command.status is not None:
            return
        command.status = status
        if session.id in self._sessions:
            session.notify(
                "rois.command.completed", CompletedParams(command_id=command_id, status=status)
            )

    def _prune_commands(self) -> None:
        """Forget the oldest finished commands beyond what the table keeps."""
        excess = len(self._commands) - _COMMANDS_KEPT
        if excess <= 0:
            return
        finished = [c for c, entry in self._commands.items() if entry.status is not None]
        for command_id in finished[:excess]:
            del self._commands[command_id]

    # -- Helpers -------------------------------------------------------------------------

    def _components(self) -> dict[str, tuple[HRIComponentProfile, ComponentContract]]:
        """Every component this engine reaches: profile and source, by ref."""
        components: dict[str, tuple[HRIComponentProfile, ComponentContract]] = {}
        for source in (self._local, *self._children):
            for ref, profile in source.profiles().items():
                components.setdefault(ref, (profile, source))
        return components

    def _profile(self, ref: str) -> HRIComponentProfile | None:
        entry = self._components().get(ref)
        return entry[0] if entry is not None else None

    def _select(self, condition: str) -> list[str] | None:
        """The refs a selection condition matches, or None when it does not parse."""
        try:
            parsed = parse_condition(condition)
        except ConditionError:
            return None
        return [
            ref
            for ref, (profile, _) in self._components().items()
            if parsed.matches(
                {COMPONENT_REF: ref, COMPONENT_TYPE: component_type_urn(profile.identifier)}
            )
        ]

    def _pick(
        self, condition: str, qualifies: Callable[[HRIComponentProfile], bool]
    ) -> tuple[str, ComponentContract] | ReturnCode:
        """The one component a condition selects among those that qualify."""
        selected = self._select(condition)
        if selected is None:
            return ReturnCode.BAD_PARAMETER
        components = self._components()
        candidates = [ref for ref in selected if qualifies(components[ref][0])]
        if not candidates:
            return ReturnCode.UNSUPPORTED
        if len(candidates) > 1:
            return ReturnCode.BAD_PARAMETER
        return candidates[0], components[candidates[0]][1]

    def _owner_of(self, assigned_id: str) -> ComponentContract | None:
        """The source that assigned an id, by the engine id it starts with."""
        engine_id, separator, _ = assigned_id.partition("/")
        if not separator:
            return None
        for source in (self._local, *self._children):
            if engine_id in source.engine_ids:
                return source
        return None

    def _bind(self, session: Session, ref: str, profile: HRIComponentProfile) -> ReturnCode:
        """Bind a component to a session. Only actuation components are reserved."""
        if profile.function is not ComponentFunction.ACTUATION:
            return ReturnCode.OK
        holder = self._bindings.get(ref)
        if holder is not None and holder != session.id:
            return ReturnCode.OUT_OF_RESOURCES
        self._bindings[ref] = session.id
        return ReturnCode.OK

    def _holds(self, session: Session, ref: str, profile: HRIComponentProfile) -> bool:
        """Whether a session may command a component."""
        if session.trusted or profile.function is not ComponentFunction.ACTUATION:
            return True
        return self._bindings.get(ref) == session.id

    def _deliverer(self, session: Session) -> Deliver:
        def deliver(event: NotifyEventParams) -> None:
            if session.id in self._sessions:
                session.notify("rois.event.notify_event", event)

        return deliver

    async def _release_session(self, session: Session) -> None:
        for ref in [r for r, holder in self._bindings.items() if holder == session.id]:
            del self._bindings[ref]
        mine = [s for s, entry in self._subscriptions.items() if entry.session_id == session.id]
        for subscribe_id in mine:
            subscription = self._subscriptions.pop(subscribe_id)
            try:
                await subscription.source.unsubscribe(subscribe_id)
            except Exception:
                logger.exception("Could not end subscription %s", subscribe_id)

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def _units(item: CommandUnitSequenceItem) -> list[CommandUnit]:
    """The commands of one item of an execute: a command, or the commands of a group."""
    return [item] if isinstance(item, CommandUnit) else list(item.command_list)


def _declares(profile: HRIComponentProfile, command_type: str) -> bool:
    """Whether a component serves a command. set_parameter needs declared parameters."""
    if command_type == "set_parameter":
        return bool(profile.parameter_profiles)
    return any(m.name == command_type for m in profile.command_profiles)


def _checked_parameters(
    profile: HRIComponentProfile, parameters: Sequence[Parameter]
) -> list[Parameter] | None:
    """Parameters with the types of the profile, or None when one does not fit."""
    types = {p.name: p.data_type_ref.code for p in profile.parameter_profiles}
    checked: list[Parameter] = []
    for parameter in parameters:
        code = types.get(parameter.name)
        if code is None:
            return None
        try:
            decode_value(code, parameter.value)
        except ValueError:
            return None
        checked.append(Parameter(name=parameter.name, data_type_ref=code, value=parameter.value))
    return checked


def _checked_arguments(profile: HRIComponentProfile, unit: CommandUnit) -> bool:
    """Whether the arguments of a command are those of its profile, with fitting values."""
    if unit.command_type == "set_parameter":
        arguments = [Parameter(name=a.name, data_type_ref=a.data_type_ref, value=a.value)
                     for a in unit.arguments]
        return _checked_parameters(profile, arguments) is not None
    message = next(m for m in profile.command_profiles if m.name == unit.command_type)
    types = {a.name: a.data_type_ref.code for a in message.arguments}
    for argument in unit.arguments:
        code = types.get(argument.name)
        if code is None:
            return False
        try:
            decode_value(code, argument.value)
        except ValueError:
            return False
    return True


def _empty_filter(condition: str) -> bool:
    """Whether a result filter is empty, the only filter defined so far."""
    try:
        parse_condition(condition, frozenset())
    except ConditionError:
        return False
    return True


def _trim(profile: HRIEngineProfileType, chosen: set[str]) -> HRIEngineProfileType | None:
    """An engine profile with only the chosen components, or None when none is left."""
    sub_profiles = [t for p in profile.sub_profiles if (t := _trim(p, chosen)) is not None]
    component_ids = [ref for ref in profile.component_ids if ref in chosen]
    if not component_ids:
        return None
    return profile.model_copy(update={"sub_profiles": sub_profiles, "component_ids": component_ids})
