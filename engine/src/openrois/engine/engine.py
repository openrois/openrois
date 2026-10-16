"""The recursive RoIS HRI Engine.

``Engine`` answers the RoIS method catalog for the sessions connected to it: clients of
a gateway, or the parent engine of an adapter. It reaches its components through the
component contract (``openrois.engine.contract``): the components it hosts in its own
process, and the components of its child engines. One class serves an adapter (local
components), a gateway (child engines) and a middle tier (both).

The engine does what is the same for every component:

- It serves a session only after ``rois.system.connect``, and answers every other
  request before it with ERROR. ``disconnect`` releases what the session held and aborts
  the sequences it had running.
- It selects components by condition, in the OpenRoIS subset of CQL2-Text. The condition
  of a query or a subscribe also carries the arguments of its message.
- It holds the binds. Every Command interface operation needs a bind from the calling
  session on the component it names. An actuation component takes one bind at a time,
  any other component one bind per session. ``release`` aborts the caller's commands
  still running on the component. Requests from a parent engine skip the check, since
  the parent made it.
- It answers ``component_status`` for the asking session: BUSY when another session
  holds an actuation component the asker cannot bind now.
- It assigns the command id of every command of an ``execute`` and returns the sequence
  with the ids. A parent engine names the ids itself, and this engine reuses them.
- It runs ``execute``: the items in order, each ``delay_time`` waited, the branches of a
  ``ConcurrentCommands`` item at the same time and each branch in order. A command that
  ends other than OK stops its branch and the items after it, whose commands complete
  with ABORT.
- It sends every ``rois.command.completed`` once, to the session that started the
  command, and every ``rois.system.notify_error`` to the sessions the error concerns.
- It routes subscriptions, results, events and errors to the source that owns them.

Clients connect to the top engine of a hierarchy, which holds the binds for every engine
below it. A middle tier serves its parent through a trusted session, so it does not
check the binds of its parent's clients against those of its own clients.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from typing import Any

from openrois.interfaces.catalog import (
    METHODS_BY_NAME,
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
from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.condition import (
    COMPONENT_REF,
    COMPONENT_TYPE,
    SELECTION_PROPERTIES,
    Condition,
    ConditionError,
    component_type_urn,
    parse_condition,
)
from openrois.interfaces.hri import (
    Argument,
    Branch,
    CommandUnit,
    CommandUnitSequenceItem,
    ConcurrentCommands,
    Parameter,
    Result,
    ReturnCode,
)
from openrois.interfaces.profiles import (
    ComponentFunction,
    HRIComponentProfile,
    HRIEngineProfileType,
    ParameterProfile,
    RoISIdentifierType,
)
from openrois.interfaces.service import (
    CompletedParams,
    CompletedStatus,
    ErrorType,
    NotifyErrorParams,
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

_STATUS_QUERY = "component_status"

#: The authority of the engine profile identifier.
ENGINE_AUTHORITY = "OpenRoIS"

type _Handler = Callable[[Session, Any], Awaitable[BaseModel]]


@dataclass(eq=False)
class _Command:
    """An entry of the command table.

    ``source`` ran the command and keeps its results. It is None for a command that
    never ran, which has no results. ``task`` runs the command while it runs, so a
    release can abort it.
    """

    session_id: str
    ref: str
    source: ComponentContract | None = None
    status: CompletedStatus | None = None
    task: asyncio.Future[CompletedStatus] | None = None


@dataclass(frozen=True, slots=True)
class _Subscription:
    session_id: str
    source: ComponentContract
    ref: str
    # The event type and the condition as parsed, so a repeated subscribe finds it.
    key: tuple[str, str]


@dataclass(eq=False)
class _Sequences:
    """The sequences a session has running."""

    tasks: set[asyncio.Task[None]] = field(default_factory=set)


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
        self._local.on_error(self._notify_error)
        self._children: list[ComponentContract] = []
        self._sessions: dict[str, Session] = {}
        self._binds: dict[str, set[str]] = {}
        self._commands: dict[str, _Command] = {}
        self._subscriptions: dict[str, _Subscription] = {}
        self._sequences: dict[str, _Sequences] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._next_session = 0
        self._next_command = 0
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
        child.on_error(self._notify_error)
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
        """Remove a child engine whose connection is gone, with its binds."""
        if child not in self._children:
            return
        refs = set(child.profiles())
        self._children.remove(child)
        for ref in refs & set(self._binds):
            del self._binds[ref]
        gone = [s for s, entry in self._subscriptions.items() if entry.source is child]
        for subscribe_id in gone:
            del self._subscriptions[subscribe_id]
        self.profile_changed()

    def child_engine_ids(self) -> list[str]:
        """The ids of the connected child engines, in the order they connected."""
        return [p.identifier.code for c in self._children if (p := c.engine_profile()) is not None]

    async def start(self) -> None:
        """Open the resources of the local components and connect the components."""
        await self._local.start()

    async def stop(self) -> None:
        """Cancel every running sequence and disconnect the local components."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._local.stop()

    # -- The status of the engine --------------------------------------------------------

    def raise_status(self, status: ComponentStatus, message: str = "") -> None:
        """Report WARNING or ERROR on the engine itself, until :meth:`clear_status`.

        Every connected session receives ``rois.system.notify_error`` with the error
        type ENGINE_INTERNAL_ERROR, and SystemInformation reports the status as its
        ``engine_status``. Safe to call from any thread.

        Raises:
            ValueError: The status is neither WARNING nor ERROR.
        """
        self._local.raise_engine_status(status, message)

    def clear_status(self) -> None:
        """Withdraw the status raised on the engine. Safe to call from any thread."""
        self._local.clear_engine_status()

    # -- Sessions ------------------------------------------------------------------------

    def open_session(self, notify: Notify, *, trusted: bool = False) -> Session:
        """Open a session for a client, or with ``trusted`` for the parent engine.

        The session is served once it has sent ``rois.system.connect``.
        """
        self._next_session += 1
        session = Session(f"session-{self._next_session}", notify, trusted)
        self._sessions[session.id] = session
        return session

    async def close_session(self, session: Session) -> None:
        """End a session whose connection is gone, as a disconnect would."""
        await self._end_session(session)
        self._sessions.pop(session.id, None)

    def profile_changed(self) -> None:
        """Tell every connected session that the engine profile changed."""
        for session in list(self._sessions.values()):
            if session.connected:
                session.notify("rois.system.profile_changed", ProfileChangedParams())

    async def handle(self, session: Session, method: str, params: BaseModel) -> BaseModel:
        """Answer one catalog request of a session with its result model.

        A session that has not connected gets ERROR on every request but connect, since
        no message flows before connect completes (spec 8.2.2.1.1).

        Args:
            session: The session that sent the request.
            method: A method of the catalog, for example ``rois.command.execute``.
            params: The params, already validated against the catalog model.

        Raises:
            KeyError: The method is not in the catalog.
        """
        handler = self._handlers[method]
        if not session.connected and method != "rois.system.connect":
            return METHODS_BY_NAME[method].result.model_validate(
                {"return_code": ReturnCode.ERROR}
            )
        return await handler(session, params)

    # -- SystemIF ------------------------------------------------------------------------

    async def _connect(self, session: Session, params: ConnectParams) -> ConnectResult:
        session.connected = True
        return ConnectResult(return_code=ReturnCode.OK)

    async def _disconnect(self, session: Session, params: DisconnectParams) -> DisconnectResult:
        await self._end_session(session)
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
        ref = params.component_ref
        if self._profile(ref) is None:
            return ReleaseResult(return_code=ReturnCode.UNSUPPORTED)
        self._binds.get(ref, set()).discard(session.id)
        # A bind that ends while the component still runs the caller's commands would
        # let the next session take an actuator mid-motion, so they end with ABORT.
        await self._abort_commands(session, ref)
        return ReleaseResult(return_code=ReturnCode.OK)

    async def _get_parameter(
        self, session: Session, params: GetParameterParams
    ) -> GetParameterResult:
        entry = self._components().get(params.component_ref)
        if entry is None:
            return GetParameterResult(return_code=ReturnCode.UNSUPPORTED)
        if not self._holds(session, params.component_ref):
            return GetParameterResult(return_code=ReturnCode.ERROR)
        return await entry[1].get_parameter(params.component_ref)

    async def _set_parameter(
        self, session: Session, params: SetParameterParams
    ) -> SetParameterResult:
        entry = self._components().get(params.component_ref)
        if entry is None:
            return SetParameterResult(return_code=ReturnCode.UNSUPPORTED)
        profile, source = entry
        if not self._holds(session, params.component_ref):
            return SetParameterResult(return_code=ReturnCode.ERROR)
        parameters = _checked_parameters(profile, params.parameters)
        if parameters is None:
            return SetParameterResult(return_code=ReturnCode.BAD_PARAMETER)
        result, status = await source.set_parameter(params.component_ref, parameters)
        if result.return_code is ReturnCode.OK and result.command_id:
            command = _Command(session.id, params.component_ref, source)
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
            # The values are applied already. The completed notification follows the
            # reply, which the connection sends before this callback runs.
            asyncio.get_running_loop().call_soon(
                self._complete, session, result.command_id, command, status
            )
        return result

    async def _execute(self, session: Session, params: ExecuteParams) -> ExecuteResult:
        units = [unit for item in params.command_unit_list for unit in _units(item)]
        if not units:
            return ExecuteResult(return_code=ReturnCode.BAD_PARAMETER)
        components = self._components()
        for unit in units:
            entry = components.get(unit.component_ref)
            if entry is None or not _declares(entry[0], unit.command_type):
                return ExecuteResult(return_code=ReturnCode.UNSUPPORTED)
        for unit in units:
            if not self._holds(session, unit.component_ref):
                return ExecuteResult(return_code=ReturnCode.ERROR)
        for unit in units:
            if not _checked_arguments(components[unit.component_ref][0], unit):
                return ExecuteResult(return_code=ReturnCode.BAD_PARAMETER)
        if session.trusted:
            # A parent engine names the ids, and this engine reuses them (Annex B.2).
            seen: set[str] = set()
            for unit in units:
                if (
                    not unit.command_id
                    or unit.command_id in self._commands
                    or unit.command_id in seen
                    or self._owner_of(unit.command_id) is not None
                ):
                    return ExecuteResult(return_code=ReturnCode.BAD_PARAMETER)
                seen.add(unit.command_id)
            items = list(params.command_unit_list)
        else:
            items = [self._assign_ids(item) for item in params.command_unit_list]
        for item in items:
            for unit in _units(item):
                source = components[unit.component_ref][1]
                self._commands[unit.command_id] = _Command(session.id, unit.component_ref, source)
        self._prune_commands()
        self._run_for(session, self._run_sequence(session, items))
        return ExecuteResult(return_code=ReturnCode.OK, command_unit_list=items)

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
        picked = self._pick(params.condition, params.query_type, events=False)
        if isinstance(picked, ReturnCode):
            return QueryResult(return_code=picked)
        ref, source, arguments, _ = picked
        result = await source.query(ref, params.query_type, arguments)
        if params.query_type == _STATUS_QUERY and result.return_code is ReturnCode.OK:
            return result.model_copy(update={"results": self._as_seen_by(session, ref, result)})
        return result

    async def _subscribe(self, session: Session, params: SubscribeParams) -> SubscribeResult:
        picked = self._pick(params.condition, params.event_type, events=True)
        if isinstance(picked, ReturnCode):
            return SubscribeResult(return_code=picked)
        ref, source, arguments, condition = picked
        key = (params.event_type, condition)
        for subscribe_id, entry in self._subscriptions.items():
            if entry.session_id == session.id and entry.key == key:
                return SubscribeResult(return_code=ReturnCode.OK, subscribe_id=subscribe_id)
        result = await source.subscribe(
            ref, params.event_type, arguments, self._deliverer(session)
        )
        if result.return_code is ReturnCode.OK:
            self._subscriptions[result.subscribe_id] = _Subscription(
                session.id, source, ref, key
            )
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

    def _assign_ids(self, item: CommandUnitSequenceItem) -> CommandUnitSequenceItem:
        """The item with a new command id on every command. A client's ids are ignored."""
        if isinstance(item, CommandUnit):
            return item.model_copy(update={"command_id": self._new_command_id()})
        branches = [
            Branch(
                command_list=[
                    u.model_copy(update={"command_id": self._new_command_id()})
                    for u in b.command_list
                ]
            )
            for b in item.branch_list
        ]
        return item.model_copy(update={"branch_list": branches})

    def _new_command_id(self) -> str:
        self._next_command += 1
        return f"{self._engine_id}/cmd-{self._next_command}"

    async def _run_sequence(
        self, session: Session, items: Sequence[CommandUnitSequenceItem]
    ) -> None:
        """Run the items of an execute in order, the branches of one item together."""
        try:
            for index, item in enumerate(items):
                if item.delay_time:
                    await asyncio.sleep(item.delay_time / 1000)
                if isinstance(item, CommandUnit):
                    ended = [await self._run_branch(session, [item], delayed=False)]
                else:
                    ended = await asyncio.gather(
                        *(
                            self._run_branch(session, branch.command_list, delayed=True)
                            for branch in item.branch_list
                        )
                    )
                if not all(ended):
                    for later in items[index + 1 :]:
                        self._skip(session, _units(later))
                    return
        except asyncio.CancelledError:
            # The session went away: every command that has not ended yet aborts.
            for item in items:
                self._skip(session, _units(item))
            raise

    async def _run_branch(
        self, session: Session, units: Sequence[CommandUnit], *, delayed: bool
    ) -> bool:
        """Run the commands of a branch in order. False when one ended other than OK.

        ``delayed`` waits the delay_time of every command first, as in a branch of a
        ConcurrentCommands item, whose delays are their own.
        """
        for index, unit in enumerate(units):
            if delayed and unit.delay_time:
                await asyncio.sleep(unit.delay_time / 1000)
            if await self._run_unit(session, unit) is not CompletedStatus.OK:
                self._skip(session, units[index + 1 :])
                return False
        return True

    async def _run_unit(self, session: Session, unit: CommandUnit) -> CompletedStatus:
        """Run one command and finish it. A release aborts it by cancelling its task."""
        command = self._commands.get(unit.command_id)
        entry = self._components().get(unit.component_ref)
        if command is None or entry is None:
            status = CompletedStatus.ERROR
        else:
            task = asyncio.ensure_future(entry[1].run(unit))
            command.task = task
            try:
                status = await task
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    # The whole sequence is cancelled: the task is cancelled with it.
                    self._finish(session, unit.command_id, CompletedStatus.ABORT)
                    raise
                status = CompletedStatus.ABORT
            except Exception:
                logger.exception("Command %s failed", unit.command_id)
                status = CompletedStatus.ERROR
            finally:
                command.task = None
        self._finish(session, unit.command_id, status)
        return status

    async def _abort_commands(self, session: Session, ref: str) -> None:
        """Abort the commands of a session still running on one component, and wait."""
        tasks = [
            command.task
            for command in self._commands.values()
            if command.session_id == session.id
            and command.ref == ref
            and command.task is not None
            and command.status is None
        ]
        self._spare_shared(session, ref)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # The sequence task finishes the command once it sees the cancellation.
        await asyncio.sleep(0)

    def _spare_shared(self, session: Session, ref: str | None = None) -> None:
        """Keep running, in a child engine, the commands of a session that others share.

        The gateway holds one bind in the child for all its clients. A command of a
        session that ends is halted in the child only when no other session still holds
        the component, so one client never aborts another's commands there. Call it after
        the binds of the session are gone.
        """
        for command_id, command in self._commands.items():
            if (
                command.session_id == session.id
                and (ref is None or command.ref == ref)
                and command.task is not None
                and command.status is None
                and command.source is not None
                and command.source is not self._local
                and self._binds.get(command.ref, set()) - {session.id}
            ):
                command.source.keep_running(command_id)

    def _skip(self, session: Session, units: Sequence[CommandUnit]) -> None:
        """End with ABORT the commands that never ran, and forget their source."""
        for unit in units:
            command = self._commands.get(unit.command_id)
            if command is not None and command.status is None and command.task is None:
                command.source = None
                self._finish(session, unit.command_id, CompletedStatus.ABORT)

    def _finish(self, session: Session, command_id: str, status: CompletedStatus) -> None:
        """Record how a command of an execute ended."""
        command = self._commands.get(command_id)
        if command is None:
            return
        self._complete(session, command_id, command, status)

    def _complete(
        self, session: Session, command_id: str, command: _Command, status: CompletedStatus
    ) -> None:
        """Record how a command ended and tell the session that started it, once."""
        if command.status is not None:
            return
        command.status = status
        if session.connected and session.id in self._sessions:
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

    # -- Errors --------------------------------------------------------------------------

    def _notify_error(self, ref: str, error_id: str, error_type: ErrorType) -> None:
        """Send an error to the sessions it concerns.

        An engine error goes to every connected session. A component error goes to the
        sessions that hold a bind or a subscription on the component, and to a trusted
        parent, which passes it up (spec 7.3: from bind until release, and while a
        subscription lasts).
        """
        params = NotifyErrorParams(error_id=error_id, error_type=error_type)
        subscribed = {s.session_id for s in self._subscriptions.values() if s.ref == ref}
        for session in list(self._sessions.values()):
            if not session.connected:
                continue
            if (
                not ref
                or session.trusted
                or session.id in self._binds.get(ref, set())
                or session.id in subscribed
            ):
                session.notify("rois.system.notify_error", params)

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
        return self._matching(parsed)

    def _matching(self, selection: Condition) -> list[str]:
        return [
            ref
            for ref, (profile, _) in self._components().items()
            if selection.matches(
                {COMPONENT_REF: ref, COMPONENT_TYPE: component_type_urn(profile.identifier)}
            )
        ]

    def _pick(
        self, condition: str, name: str, *, events: bool
    ) -> tuple[str, ComponentContract, list[Argument], str] | ReturnCode:
        """The one component a query or a subscribe selects, and its arguments.

        The condition selects with component_ref and component_type, and gives the
        arguments of the message with ``=``, for example ``stream_id = 'audio-1'``.
        Returns the ref, its source, the arguments and the condition as parsed.
        """
        components = self._components()

        def messages(profile: HRIComponentProfile) -> list[Any]:
            found = profile.event_profiles if events else profile.query_profiles
            return [m for m in found if m.name == name]

        argument_names = {
            a.name
            for profile, _ in components.values()
            for m in messages(profile)
            for a in m.arguments
        }
        try:
            parsed = parse_condition(condition, SELECTION_PROPERTIES | argument_names)
        except ConditionError:
            return ReturnCode.BAD_PARAMETER
        selection = Condition(
            tuple(c for c in parsed.comparisons if c.property in SELECTION_PROPERTIES)
        )
        given = [c for c in parsed.comparisons if c.property not in SELECTION_PROPERTIES]
        candidates = [ref for ref in self._matching(selection) if messages(components[ref][0])]
        if not candidates:
            return ReturnCode.UNSUPPORTED
        if len(candidates) > 1:
            return ReturnCode.BAD_PARAMETER
        ref = candidates[0]
        [message] = messages(components[ref][0])
        types = {a.name: a.data_type_ref.code for a in message.arguments}
        arguments: dict[str, Argument] = {}
        for comparison in given:
            code = types.get(comparison.property)
            if code is None or comparison.operator != "=":
                return ReturnCode.BAD_PARAMETER
            known = arguments.get(comparison.property)
            if known is not None and known.value != comparison.value:
                return ReturnCode.BAD_PARAMETER
            try:
                decode_value(code, comparison.value)
            except ValueError:
                return ReturnCode.BAD_PARAMETER
            arguments[comparison.property] = Argument(
                name=comparison.property, data_type_ref=code, value=comparison.value
            )
        return ref, components[ref][1], list(arguments.values()), str(parsed)

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
        """Bind a component to a session.

        An actuation component takes one bind at a time. Any other component, one
        without a RoSO function included, takes one bind per session (Table 8.40).
        """
        holders = self._binds.setdefault(ref, set())
        if session.id in holders:
            return ReturnCode.OK
        if profile.function is ComponentFunction.ACTUATION and holders:
            return ReturnCode.OUT_OF_RESOURCES
        holders.add(session.id)
        return ReturnCode.OK

    def _holds(self, session: Session, ref: str) -> bool:
        """Whether a session may use the Command interface on a component."""
        return session.trusted or session.id in self._binds.get(ref, set())

    def _as_seen_by(self, session: Session, ref: str, result: QueryResult) -> list[Result]:
        """The component_status results for one session: BUSY when it cannot bind now."""
        profile = self._profile(ref)
        others = self._binds.get(ref, set()) - {session.id}
        busy = profile is not None and profile.function is ComponentFunction.ACTUATION and others
        return [
            r.model_copy(update={"value": ComponentStatus.BUSY.value})
            if busy and r.name == "status" and r.value == ComponentStatus.READY.value
            else r
            for r in result.results
        ]

    def _deliverer(self, session: Session) -> Deliver:
        def deliver(event: NotifyEventParams) -> None:
            if session.connected and session.id in self._sessions:
                session.notify("rois.event.notify_event", event)

        return deliver

    async def _end_session(self, session: Session) -> None:
        """Abort the sequences of a session and release its binds and subscriptions."""
        session.connected = False
        for holders in self._binds.values():
            holders.discard(session.id)
        self._spare_shared(session)
        running = self._sequences.pop(session.id, None)
        if running is not None:
            for task in running.tasks:
                task.cancel()
            await asyncio.gather(*running.tasks, return_exceptions=True)
        mine = [s for s, entry in self._subscriptions.items() if entry.session_id == session.id]
        for subscribe_id in mine:
            subscription = self._subscriptions.pop(subscribe_id)
            try:
                await subscription.source.unsubscribe(subscribe_id)
            except Exception:
                logger.exception("Could not end subscription %s", subscribe_id)

    def _run_for(self, session: Session, coroutine: Coroutine[Any, Any, None]) -> None:
        """Run a sequence of a session, which a disconnect of the session aborts."""
        task = asyncio.create_task(coroutine)
        running = self._sequences.setdefault(session.id, _Sequences())
        running.tasks.add(task)
        task.add_done_callback(running.tasks.discard)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def _units(item: CommandUnitSequenceItem) -> list[CommandUnit]:
    """The commands of one item of an execute: a command, or every command of a group."""
    if isinstance(item, ConcurrentCommands):
        return [unit for branch in item.branch_list for unit in branch.command_list]
    return [item]


def _declares(profile: HRIComponentProfile, command_type: str) -> bool:
    """Whether a component serves a command. set_parameter needs declared parameters."""
    if command_type == "set_parameter":
        return bool(profile.parameter_profiles)
    return any(m.name == command_type for m in profile.command_profiles)


def _checked_parameters(
    profile: HRIComponentProfile, parameters: Sequence[Parameter]
) -> list[Parameter] | None:
    """Parameters with the types of the profile, or None when one may not be set.

    A name the profile does not list, a read-only parameter and a value that does not
    fit its type are refused, and then none of the values is applied.
    """
    declared: dict[str, ParameterProfile] = {p.name: p for p in profile.parameter_profiles}
    checked: list[Parameter] = []
    for parameter in parameters:
        known = declared.get(parameter.name)
        if known is None or known.read_only:
            return None
        code = known.data_type_ref.code
        try:
            decode_value(code, parameter.value)
        except ValueError:
            return None
        checked.append(Parameter(name=parameter.name, data_type_ref=code, value=parameter.value))
    return checked


def _checked_arguments(profile: HRIComponentProfile, unit: CommandUnit) -> bool:
    """Whether the arguments of a command are those of its profile, with fitting values."""
    if unit.command_type == "set_parameter":
        arguments = [
            Parameter(name=a.name, data_type_ref=a.data_type_ref, value=a.value)
            for a in unit.arguments
        ]
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
