"""A child engine: an adapter or a lower gateway, reached over the method catalog.

``ChildEngine`` implements the component contract for the components of one child
engine. It sends the child the same catalog requests a client would send, and turns
the child's notifications back into the engine's callbacks. The parent engine is the
child's only client, so the child skips the bind checks the parent already made.

Ids stay the same end to end: refs and the ids the child assigns start with the id of
the engine that owns the component, and command ids are named by the client. A reply
that assigns an id outside the child's engine ids counts as ERROR.

A request that times out may still take effect on the child. A subscription whose reply
comes too late is ended, since nobody holds it. A command keeps running, and a parameter
value is applied, as RoIS has no way to take them back.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from openrois.interfaces.catalog import (
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
    SetParameterParams,
    SetParameterResult,
    SubscribeParams,
    SubscribeResult,
    UnsubscribeParams,
    UnsubscribeResult,
)
from openrois.interfaces.condition import COMPONENT_REF, eq
from openrois.interfaces.hri import CommandUnit, Parameter, ReturnCode
from openrois.interfaces.profiles import HRIComponentProfile, HRIEngineProfileType
from openrois.interfaces.service import CompletedParams, CompletedStatus, NotifyEventParams
from pydantic import BaseModel, ValidationError

from openrois.engine.contract import Deliver, OnCompleted

logger = logging.getLogger(__name__)

_JSONRPC_VERSION = "2.0"

# Checks an OK reply before the caller sees it, and records what the next messages need.
# Returning False turns the reply into ERROR.
type _OnReply = Callable[[Any], bool]

# A request waiting for its reply: the future, the result model, and the hook for an OK.
type _Pending = tuple[asyncio.Future[BaseModel], type[BaseModel], _OnReply | None]

# What to do with an OK reply that arrives after its caller stopped waiting.
type _OnLate = Callable[[Any], None]

# How many requests whose caller stopped waiting are remembered for a late reply.
_LATE_KEPT = 1024

# The completion status of a command the child refused to start, by return code.
_REFUSED_STATUS = {
    ReturnCode.OUT_OF_RESOURCES: CompletedStatus.OUT_OF_RESOURCES,
    ReturnCode.TIMEOUT: CompletedStatus.TIMEOUT,
}


class ChildEngine:
    """The component contract for one child engine on a WebSocket connection.

    The connection's reader passes every message from the child to :meth:`handle`,
    in order, on the event loop. A reply is matched to its request, and work that must
    happen before the next message, such as recording a new subscription, happens right
    there.
    """

    def __init__(
        self,
        send: Callable[[str], Awaitable[None]],
        *,
        request_timeout: float = 10.0,
        check_engine_ids: Callable[[ChildEngine, frozenset[str]], None] | None = None,
        on_profile_changed: Callable[[], None] | None = None,
        on_refused: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the proxy of a child engine that has not been discovered yet.

        Args:
            send: Sends one text message to the child.
            request_timeout: Seconds to wait for the child's reply to a request
                before answering TIMEOUT. Commands themselves may run longer.
            check_engine_ids: Raises ValueError for engine ids of the child that
                another engine in the tree already uses, such as
                ``Engine.check_engine_ids``. Every profile of the child goes through
                it, the first one and every changed one.
            on_profile_changed: Called after the child's profile changed and was
                read again.
            on_refused: Called with the reason when a changed profile breaks the rules
                discovery checks. It closes the connection, as discovery would have.
        """
        self._send = send
        self._request_timeout = request_timeout
        self._check_engine_ids = check_engine_ids
        self._on_profile_changed = on_profile_changed
        self._on_refused = on_refused
        self._open = True
        self._next_id = 0
        self._pending: dict[int, _Pending] = {}
        self._late: dict[int, tuple[type[BaseModel], _OnLate]] = {}
        self._running: dict[str, asyncio.Future[CompletedStatus]] = {}
        self._on_completed: dict[str, OnCompleted] = {}
        self._deliveries: dict[str, Deliver] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._profile: HRIEngineProfileType | None = None
        self._profiles: dict[str, HRIComponentProfile] = {}
        self._engine_ids: frozenset[str] = frozenset()

    @property
    def engine_id(self) -> str:
        """The id of the child engine, empty before discovery."""
        return self._profile.identifier.code if self._profile is not None else ""

    # -- Connection ----------------------------------------------------------------------

    async def discover(self) -> None:
        """Read the child's profile. Call once, after the reader has started.

        Raises:
            ValueError: The child did not answer with a profile, or the profile names
                an invalid engine id or a component ref no engine in it owns.
        """
        result = await self._request(
            "rois.system.get_profile", GetProfileParams(condition=""), GetProfileResult
        )
        if result.return_code is not ReturnCode.OK or result.profile is None:
            raise ValueError(f"Discovery failed with {result.return_code.value}.")
        self._apply_profile(result)

    def handle(self, message: Mapping[str, Any]) -> None:
        """Route one message from the child: a reply or a notification."""
        if "id" in message and "method" not in message:
            self._handle_reply(message)
        elif "method" in message and "id" not in message:
            # A reply wakes its caller with call_soon, so a notification queued the same
            # way runs after the caller has passed the reply on. The client of a gateway
            # thus reads the reply to subscribe before the first event of the
            # subscription, and the reply to set_parameter before its completion.
            asyncio.get_running_loop().call_soon(
                self._handle_notification, str(message["method"]), message.get("params", {})
            )
        else:
            logger.warning("Child engine %s sent a request, which it may not do.", self.engine_id)

    def detach(self) -> None:
        """Forget the connection: fail what still waits on the child."""
        self._open = False
        for future, result_type, _ in self._pending.values():
            if not future.done():
                future.set_result(result_type.model_validate({"return_code": ReturnCode.ERROR}))
        self._pending.clear()
        self._late.clear()
        for running in self._running.values():
            if not running.done():
                running.set_result(CompletedStatus.ERROR)
        self._running.clear()
        for command_id, on_completed in list(self._on_completed.items()):
            on_completed(command_id, CompletedStatus.ERROR)
        self._on_completed.clear()
        self._deliveries.clear()
        for task in self._tasks:
            task.cancel()

    # -- The component contract ----------------------------------------------------------

    @property
    def engine_ids(self) -> frozenset[str]:
        return self._engine_ids

    def profiles(self) -> Mapping[str, HRIComponentProfile]:
        return self._profiles

    def engine_profile(self) -> HRIEngineProfileType | None:
        return self._profile

    async def run(self, unit: CommandUnit) -> CompletedStatus:
        future: asyncio.Future[CompletedStatus] = asyncio.get_running_loop().create_future()
        self._running[unit.command_id] = future
        # This engine waited the delay already, so the child must not wait it again.
        command = unit.model_copy(update={"delay_time": None})
        try:
            reply = await self._request(
                "rois.command.execute", ExecuteParams(command_unit_list=[command]), ExecuteResult
            )
            if reply.return_code is not ReturnCode.OK:
                return _REFUSED_STATUS.get(reply.return_code, CompletedStatus.ERROR)
            return await future
        finally:
            self._running.pop(unit.command_id, None)

    async def set_parameter(
        self,
        ref: str,
        parameters: Sequence[Parameter],
        on_completed: OnCompleted,
    ) -> SetParameterResult:
        def record(result: SetParameterResult) -> bool:
            if not self._owns(result.command_id) or result.command_id in self._on_completed:
                return False
            self._on_completed[result.command_id] = on_completed
            return True

        return await self._request(
            "rois.command.set_parameter",
            SetParameterParams(component_ref=ref, parameters=list(parameters)),
            SetParameterResult,
            record,
        )

    async def get_parameter(self, ref: str) -> GetParameterResult:
        return await self._request(
            "rois.command.get_parameter", GetParameterParams(component_ref=ref), GetParameterResult
        )

    async def command_result(self, command_id: str) -> GetCommandResultResult:
        return await self._request(
            "rois.command.get_command_result",
            GetCommandResultParams(command_id=command_id, condition=""),
            GetCommandResultResult,
        )

    async def query(self, ref: str, query_type: str) -> QueryResult:
        return await self._request(
            "rois.query.query",
            QueryParams(query_type=query_type, condition=eq(COMPONENT_REF, ref)),
            QueryResult,
        )

    async def subscribe(self, ref: str, event_type: str, deliver: Deliver) -> SubscribeResult:
        recorded = False

        def record(result: SubscribeResult) -> bool:
            nonlocal recorded
            if not self._owns(result.subscribe_id) or result.subscribe_id in self._deliveries:
                return False
            self._deliveries[result.subscribe_id] = deliver
            recorded = True
            return True

        def end_late(result: SubscribeResult) -> None:
            # Nobody holds a subscription whose reply came too late, so end it. An id
            # that another request recorded belongs to a subscription someone holds.
            if not self._owns(result.subscribe_id):
                return
            if result.subscribe_id in self._deliveries and not recorded:
                return
            self._spawn(self.unsubscribe(result.subscribe_id))

        return await self._request(
            "rois.event.subscribe",
            SubscribeParams(event_type=event_type, condition=eq(COMPONENT_REF, ref)),
            SubscribeResult,
            record,
            end_late,
        )

    async def unsubscribe(self, subscribe_id: str) -> None:
        self._deliveries.pop(subscribe_id, None)
        await self._request(
            "rois.event.unsubscribe",
            UnsubscribeParams(subscribe_id=subscribe_id),
            UnsubscribeResult,
        )

    async def event_detail(self, event_id: str) -> GetEventDetailResult:
        return await self._request(
            "rois.event.get_event_detail",
            GetEventDetailParams(event_id=event_id, condition=""),
            GetEventDetailResult,
        )

    async def error_detail(self, error_id: str) -> GetErrorDetailResult:
        return await self._request(
            "rois.system.get_error_detail",
            GetErrorDetailParams(error_id=error_id, condition=""),
            GetErrorDetailResult,
        )

    # -- Requests ------------------------------------------------------------------------

    async def _request[R: BaseModel](
        self,
        method: str,
        params: BaseModel,
        result_type: type[R],
        on_reply: Callable[[R], bool] | None = None,
        on_late: Callable[[R], None] | None = None,
    ) -> R:
        """Send one request and wait for its reply.

        ``on_reply`` runs when an OK reply arrives, before the next message from the
        child is handled, and turns the reply into ERROR by returning False. A child
        that fails answers ERROR, and one that is too slow answers TIMEOUT. ``on_late``
        runs when an OK reply arrives after the caller stopped waiting, because of the
        timeout or because the caller was cancelled.
        """
        failed = result_type.model_validate({"return_code": ReturnCode.ERROR})
        if not self._open:
            return failed
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[BaseModel] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (future, result_type, on_reply)
        message = {
            "jsonrpc": _JSONRPC_VERSION,
            "id": request_id,
            "method": method,
            "params": params.model_dump(mode="json"),
        }
        try:
            await self._send(json.dumps(message))
            async with asyncio.timeout(self._request_timeout):
                reply = await future
        except TimeoutError:
            logger.warning("Child engine %s did not answer %s in time.", self.engine_id, method)
            self._remember_late(request_id, result_type, on_late)
            return result_type.model_validate({"return_code": ReturnCode.TIMEOUT})
        except asyncio.CancelledError:
            # Cancelling the caller cancels the future it waits on, unless the reply
            # had already resolved it.
            if future.cancelled() or not future.done():
                self._remember_late(request_id, result_type, on_late)
            elif on_late is not None:
                # The reply came, but the caller is gone before it could pass it on.
                arrived = future.result()
                if isinstance(arrived, result_type) and _is_ok(arrived):
                    on_late(arrived)
            raise
        except Exception:
            logger.exception("Could not send %s to child engine %s", method, self.engine_id)
            return failed
        finally:
            self._pending.pop(request_id, None)
        assert isinstance(reply, result_type)
        return reply

    def _remember_late(
        self, request_id: int, result_type: type[BaseModel], on_late: _OnLate | None
    ) -> None:
        if on_late is None:
            return
        self._late[request_id] = (result_type, on_late)
        while len(self._late) > _LATE_KEPT:
            del self._late[next(iter(self._late))]

    def _handle_reply(self, message: Mapping[str, Any]) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        entry = self._pending.pop(request_id, None)
        if entry is None:
            late = self._late.pop(request_id, None)
            if late is not None:
                reply = self._reply_of(message, late[0])
                if _is_ok(reply):
                    late[1](reply)
            return
        future, result_type, on_reply = entry
        reply = self._reply_of(message, result_type)
        if on_reply is not None and _is_ok(reply) and not on_reply(reply):
            logger.warning(
                "Child engine %s assigned an id outside its engine ids, or one in use.",
                self.engine_id,
            )
            reply = result_type.model_validate({"return_code": ReturnCode.ERROR})
        if not future.done():
            future.set_result(reply)

    def _reply_of(self, message: Mapping[str, Any], result_type: type[BaseModel]) -> BaseModel:
        """The result model of a reply, or ERROR for an error or a reply outside the catalog."""
        if "error" in message:
            logger.warning(
                "Child engine %s answered an error: %s", self.engine_id, message["error"]
            )
            return result_type.model_validate({"return_code": ReturnCode.ERROR})
        try:
            return result_type.model_validate(message.get("result"))
        except ValidationError:
            logger.warning("Child engine %s sent a reply outside the catalog.", self.engine_id)
            return result_type.model_validate({"return_code": ReturnCode.ERROR})

    def _owns(self, assigned_id: str) -> bool:
        """Whether an id starts with the id of an engine of the child, and a slash."""
        engine_id, separator, rest = assigned_id.partition("/")
        return bool(separator and rest) and engine_id in self._engine_ids

    def _handle_notification(self, method: str, params: Any) -> None:
        try:
            if method == "rois.command.completed":
                completed = CompletedParams.model_validate(params)
                running = self._running.get(completed.command_id)
                if running is not None:
                    if not running.done():
                        running.set_result(completed.status)
                elif (callback := self._on_completed.pop(completed.command_id, None)) is not None:
                    callback(completed.command_id, completed.status)
            elif method == "rois.event.notify_event":
                event = NotifyEventParams.model_validate(params)
                deliver = self._deliveries.get(event.subscribe_id)
                if deliver is not None:
                    deliver(event)
            elif method == "rois.system.profile_changed":
                self._spawn(self._rediscover())
            elif method == "rois.system.notify_error":
                logger.warning("Child engine %s reported an error: %s", self.engine_id, params)
        except ValidationError:
            logger.warning(
                "Child engine %s sent a %s outside the catalog.", self.engine_id, method
            )

    # -- Profile -------------------------------------------------------------------------

    def _apply_profile(self, result: GetProfileResult) -> None:
        profile = result.profile
        assert profile is not None
        engine_ids = _engine_ids(profile)
        for engine_id in engine_ids:
            if not engine_id or "/" in engine_id:
                raise ValueError(
                    f"Invalid engine id {engine_id!r}: it must be non-empty and free of slashes."
                )
            if engine_ids.count(engine_id) > 1:
                raise ValueError(f"Engine id {engine_id} appears twice in the child.")
        profiles: dict[str, HRIComponentProfile] = {}
        for ref in profile.component_ids:
            owner = ref.split("/", 1)[0]
            if "/" not in ref or owner not in engine_ids:
                raise ValueError(
                    f"Component ref {ref!r} does not start with an engine id of the child."
                )
            if ref not in result.component_profiles:
                raise ValueError(f"The child engine sent no profile for {ref!r}.")
            profiles[ref] = result.component_profiles[ref]
        if self._check_engine_ids is not None:
            self._check_engine_ids(self, frozenset(engine_ids))
        self._profile = profile
        self._profiles = profiles
        self._engine_ids = frozenset(engine_ids)

    async def _rediscover(self) -> None:
        result = await self._request(
            "rois.system.get_profile", GetProfileParams(condition=""), GetProfileResult
        )
        if result.return_code is not ReturnCode.OK or result.profile is None:
            logger.warning("Could not read the changed profile of child engine %s.", self.engine_id)
            return
        try:
            self._apply_profile(result)
        except ValueError as exc:
            logger.warning(
                "Refused the changed profile of child engine %s: %s", self.engine_id, exc
            )
            if self._on_refused is not None:
                await self._on_refused(str(exc))
            return
        if self._on_profile_changed is not None:
            self._on_profile_changed()

    def _spawn(self, coroutine: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def _is_ok(reply: BaseModel) -> bool:
    return getattr(reply, "return_code", None) is ReturnCode.OK


def _engine_ids(profile: HRIEngineProfileType) -> list[str]:
    """The id of an engine and of every engine below it."""
    ids = [profile.identifier.code]
    for sub_profile in profile.sub_profiles:
        ids.extend(_engine_ids(sub_profile))
    return ids
