"""RoISClient: the client of the OpenRoIS Python client SDK.

One method per operation of the RoIS method catalog, named after the IDL operation and
taking its ``in`` parameters in IDL order:

    System   connect, disconnect, get_profile, get_error_detail
    Command  search, bind, bind_any, release, get_parameter, set_parameter, execute,
             get_command_result
    Query    query
    Event    subscribe, unsubscribe, get_event_detail

A streaming component is driven with these same methods. Carrying its media is planned.

Every call goes through one path that validates the params and the result against the
models of the method catalog in openrois-interfaces, and turns a return code other than OK
into a RoISError. Notifications from the engine are validated the same way before listeners
receive their params. Inputs take a model or a mapping. A command needs no ``command_id``,
because the field defaults to an empty string that the engine replaces.

Usage:
    from openrois.sdk import RoISClient, component_ref

    async with RoISClient.connect("ws://127.0.0.1:8765") as client:
        nav = "robot_1/navigation"
        status = await client.query("component_status", component_ref(nav))

        # Listen before the call, because a command can end before the reply is read.
        ended: dict[str, str] = {}
        client.on("rois.command.completed", lambda p: ended.update({p.command_id: p.status}))

        await client.bind(nav)
        [command_id] = await client.execute([{"component_ref": nav, "command_type": "start"}])
        # ... later: ended[command_id] is "OK" once the navigation has ended.
        await client.release(nav)

Wire binding: docs/rois-reference.md section 17.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Self, overload

from openrois.interfaces import (
    METHODS_BY_NAME,
    NOTIFICATIONS_BY_NAME,
    BindAnyResult,
    CommandUnitSequenceItem,
    CompletedParams,
    ConcurrentCommands,
    ExecuteResult,
    GetCommandResultResult,
    GetErrorDetailResult,
    GetEventDetailResult,
    GetParameterResult,
    GetProfileResult,
    HRIComponentProfile,
    HRIEngineProfileType,
    NotifyErrorParams,
    NotifyEventParams,
    Parameter,
    ProfileChangedParams,
    QueryResult,
    Result,
    ReturnCode,
    SearchResult,
    SetParameterResult,
    SubscribeResult,
)
from pydantic import ValidationError

from openrois.sdk.errors import RoISError, TransportError
from openrois.sdk.transport import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_REQUEST_TIMEOUT,
    Emitter,
    JsonRpcNotification,
    Listener,
    WebSocketTransport,
)


@dataclass(frozen=True, slots=True)
class EngineProfile:
    """The get_profile result of an engine that answered OK.

    Attributes:
        profile: The engine profile, as HRIEngineProfileType in XML-Profiles.xsd defines it.
        component_profiles: The profile of every component in ``profile.component_ids``,
            keyed by fully qualified ref. An OpenRoIS extension
            (docs/rois-reference.md section 17.3).
    """

    profile: HRIEngineProfileType
    component_profiles: dict[str, HRIComponentProfile]


class Connecting:
    """What ``RoISClient.connect`` returns, both awaitable and an async context manager.

    It is both so that a caller writes ``await`` or ``async with``, without the awkward
    ``async with await``, as ``websockets.connect`` allows.
    """

    def __init__(self, url: str, request_timeout: float, connect_timeout: float) -> None:
        self._url = url
        self._request_timeout = request_timeout
        self._connect_timeout = connect_timeout
        self._client: RoISClient | None = None

    def __await__(self) -> Generator[Any, None, RoISClient]:
        return self._open().__await__()

    async def __aenter__(self) -> RoISClient:
        self._client = await self._open()
        return self._client

    async def __aexit__(self, *exc_info: object) -> None:
        assert self._client is not None
        await self._client.disconnect()

    async def _open(self) -> RoISClient:
        """Open the WebSocket and run rois.system.connect."""
        wire = WebSocketTransport(
            request_timeout=self._request_timeout,
            connect_timeout=self._connect_timeout,
        )
        await wire.connect(self._url)
        client = RoISClient(wire)
        try:
            await client._call("rois.system.connect")
        except BaseException:
            # Started and not awaited, because a peer that stopped answering would hold the
            # caller for the whole closing handshake, past any deadline of its own.
            wire._start_close()
            raise
        return client


class RoISClient(Emitter):
    """A connection to an OpenRoIS engine, with one method per RoIS operation.

    Create it with ``RoISClient.connect``. One client is one session: bindings and
    subscriptions end with it, and nothing reconnects by itself.

    Listen with ``on`` and ``off``. A plain function runs inline in the reader of the socket,
    so it must not block. A coroutine function runs in a task of its own:

        rois.event.notify_event      NotifyEventParams, for every event of a subscription
        rois.command.completed       CompletedParams, when a command ends
        rois.system.notify_error     NotifyErrorParams, when the engine reports an error
        rois.system.profile_changed  ProfileChangedParams, when components join or leave
        close                        (code, reason) when the connection closes
        error                        An exception, for a message that cannot be used or a
                                     listener that raises. With no listener it is logged.
    """

    def __init__(self, transport: WebSocketTransport) -> None:
        """Wrap a transport that is already connected. Use ``RoISClient.connect`` instead."""
        super().__init__()
        self._wire = transport
        self._connected = True
        self._disconnecting: asyncio.Future[None] | None = None
        transport.on("notification", self._on_notification)
        transport.on("close", self._on_close)
        transport.on("error", self._on_error)

    @property
    def transport(self) -> WebSocketTransport:
        """The transport under the client, for JSON-RPC methods outside the catalog.

        The client does not validate what is sent through it.
        """
        return self._wire

    @overload
    def on(
        self, name: Literal["rois.event.notify_event"], listener: Listener[NotifyEventParams]
    ) -> Self: ...
    @overload
    def on(
        self, name: Literal["rois.command.completed"], listener: Listener[CompletedParams]
    ) -> Self: ...
    @overload
    def on(
        self, name: Literal["rois.system.notify_error"], listener: Listener[NotifyErrorParams]
    ) -> Self: ...
    @overload
    def on(
        self,
        name: Literal["rois.system.profile_changed"],
        listener: Listener[ProfileChangedParams],
    ) -> Self: ...
    @overload
    def on(self, name: Literal["close"], listener: Listener[int, str]) -> Self: ...
    @overload
    def on(self, name: Literal["error"], listener: Listener[Exception]) -> Self: ...
    def on(self, name: str, listener: Callable[..., object]) -> Self:
        """Add a listener. It stays until ``off`` removes it."""
        return self._add_listener(name, listener)

    @overload
    def off(
        self, name: Literal["rois.event.notify_event"], listener: Listener[NotifyEventParams]
    ) -> Self: ...
    @overload
    def off(
        self, name: Literal["rois.command.completed"], listener: Listener[CompletedParams]
    ) -> Self: ...
    @overload
    def off(
        self, name: Literal["rois.system.notify_error"], listener: Listener[NotifyErrorParams]
    ) -> Self: ...
    @overload
    def off(
        self,
        name: Literal["rois.system.profile_changed"],
        listener: Listener[ProfileChangedParams],
    ) -> Self: ...
    @overload
    def off(self, name: Literal["close"], listener: Listener[int, str]) -> Self: ...
    @overload
    def off(self, name: Literal["error"], listener: Listener[Exception]) -> Self: ...
    def off(self, name: str, listener: Callable[..., object]) -> Self:
        """Remove a listener added with ``on``."""
        return self._remove_listener(name, listener)

    # -----------------------------------------------------------------------
    # SystemIF
    # -----------------------------------------------------------------------

    @classmethod
    def connect(
        cls,
        url: str,
        *,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    ) -> Connecting:
        """Open a connection to an engine and run rois.system.connect.

        Write ``await RoISClient.connect(url)``, or ``async with RoISClient.connect(url) as
        client`` to disconnect when the block ends.

        Args:
            url: The engine's WebSocket URL, for example ``ws://127.0.0.1:8765``.
            request_timeout: The seconds a request waits for its reply.
            connect_timeout: The seconds the WebSocket has to open.

        Raises:
            RoISConnectionError: The WebSocket cannot be opened.
            RoISError: The engine answers connect with a code other than OK.
        """
        return Connecting(url, request_timeout, connect_timeout)

    async def disconnect(self) -> None:
        """Run rois.system.disconnect and close the connection.

        The connection closes even when the engine answers with an error. Safe to call more
        than once. Calls that overlap send one rois.system.disconnect and share its outcome.
        """
        if self._disconnecting is None:
            self._disconnecting = asyncio.ensure_future(self._end_session())
        # Shielded, so that one caller who gives up leaves the others their outcome.
        await asyncio.shield(self._disconnecting)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.disconnect()

    async def get_profile(self, condition: str = "") -> EngineProfile:
        """Read the engine profile and the profiles of its components.

        Args:
            condition: Selects the components the profile lists. Empty lists all.
        """
        result: GetProfileResult = await self._call("rois.system.get_profile", condition=condition)
        if result.profile is None:
            raise TransportError("rois.system.get_profile returned OK without a profile")
        return EngineProfile(result.profile, result.component_profiles)

    async def get_error_detail(self, error_id: str, condition: str = "") -> list[Result]:
        """Read the details of an error from a rois.system.notify_error notification.

        Args:
            error_id: The ``error_id`` of the notification.
            condition: Filter on the results. Must be empty for now.
        """
        result: GetErrorDetailResult = await self._call(
            "rois.system.get_error_detail", error_id=error_id, condition=condition
        )
        return result.results

    # -----------------------------------------------------------------------
    # CommandIF
    # -----------------------------------------------------------------------

    async def search(self, condition: str = "") -> list[str]:
        """Find components.

        Args:
            condition: Selects the components. Empty matches every component.

        Returns:
            Their fully qualified refs.
        """
        result: SearchResult = await self._call("rois.command.search", condition=condition)
        return result.component_ref_list

    async def bind(self, component_ref: str) -> None:
        """Reserve a component for this client."""
        await self._call("rois.command.bind", component_ref=component_ref)

    async def bind_any(self, condition: str = "") -> str:
        """Reserve one of the components a condition selects, chosen by the engine.

        Returns:
            The ref of the reserved component.
        """
        result: BindAnyResult = await self._call("rois.command.bind_any", condition=condition)
        return result.component_ref

    async def release(self, component_ref: str) -> None:
        """Release a component reserved with ``bind`` or ``bind_any``."""
        await self._call("rois.command.release", component_ref=component_ref)

    async def get_parameter(self, component_ref: str) -> list[Parameter]:
        """Read the current value of every parameter of a component."""
        result: GetParameterResult = await self._call(
            "rois.command.get_parameter", component_ref=component_ref
        )
        return result.parameters

    async def set_parameter(
        self, component_ref: str, parameters: Sequence[Parameter | Mapping[str, Any]]
    ) -> str:
        """Set parameters of a component.

        Returns:
            The command_id the engine assigned to the change. Its rois.command.completed
            notification reports when the change took effect.
        """
        result: SetParameterResult = await self._call(
            "rois.command.set_parameter", component_ref=component_ref, parameters=parameters
        )
        return result.command_id

    async def execute(
        self, command_unit_list: Sequence[CommandUnitSequenceItem | Mapping[str, Any]]
    ) -> list[str]:
        """Run commands in order.

        A ConcurrentCommands item runs its branches at the same time, and each branch runs
        its commands in order.

        The engine answers as soon as it accepts the commands, with the command_id it
        assigned to each one. Each command then ends with a rois.command.completed
        notification carrying that command_id, and ``get_command_result`` reads its results.

        Args:
            command_unit_list: The commands, without command ids.

        Returns:
            The command_id the engine assigned to every command, in the order the list gives
            them, with the commands of a ConcurrentCommands item branch by branch.
        """
        result: ExecuteResult = await self._call(
            "rois.command.execute", command_unit_list=command_unit_list
        )
        ids: list[str] = []
        for item in result.command_unit_list:
            if isinstance(item, ConcurrentCommands):
                for branch in item.branch_list:
                    ids.extend(unit.command_id for unit in branch.command_list)
            else:
                ids.append(item.command_id)
        return ids

    async def get_command_result(self, command_id: str, condition: str = "") -> list[Result]:
        """Read the results of a command.

        Args:
            command_id: The command, by the id ``execute`` returned.
            condition: Filter on the results. Must be empty for now.
        """
        result: GetCommandResultResult = await self._call(
            "rois.command.get_command_result", command_id=command_id, condition=condition
        )
        return result.results

    # -----------------------------------------------------------------------
    # QueryIF
    # -----------------------------------------------------------------------

    async def query(self, query_type: str, condition: str = "") -> list[Result]:
        """Run a query and wait for its results.

        The engine sends the query to the one component that declares ``query_type`` and
        matches the condition. It returns UNSUPPORTED when none does, and BAD_PARAMETER when
        several do.

        Args:
            query_type: The query name from a component profile, for example
                ``component_status``.
            condition: Selects the component, for example
                ``component_ref("reachy_real/head")``.
        """
        result: QueryResult = await self._call(
            "rois.query.query", query_type=query_type, condition=condition
        )
        return result.results

    # -----------------------------------------------------------------------
    # EventIF
    # -----------------------------------------------------------------------

    async def subscribe(self, event_type: str, condition: str = "") -> str:
        """Subscribe to an event.

        Its occurrences arrive as rois.event.notify_event notifications, which carry the
        subscribe_id this returns. The engine subscribes to the one component that declares
        ``event_type`` and matches the condition, with the same rules as ``query``.

        Returns:
            The subscribe_id, for ``unsubscribe``.
        """
        result: SubscribeResult = await self._call(
            "rois.event.subscribe", event_type=event_type, condition=condition
        )
        return result.subscribe_id

    async def unsubscribe(self, subscribe_id: str) -> None:
        """Cancel a subscription. The engine ignores an id it does not know, as RoIS requires."""
        await self._call("rois.event.unsubscribe", subscribe_id=subscribe_id)

    async def get_event_detail(self, event_id: str, condition: str = "") -> list[Result]:
        """Read the payload of an event until it expires.

        Args:
            event_id: The ``event_id`` of the notification.
            condition: Filter on the results. Must be empty for now.
        """
        result: GetEventDetailResult = await self._call(
            "rois.event.get_event_detail", event_id=event_id, condition=condition
        )
        return result.results

    # -----------------------------------------------------------------------
    # Private
    # -----------------------------------------------------------------------

    async def _end_session(self) -> None:
        """The work of ``disconnect``, once for all the calls that overlap."""
        try:
            if self._connected:
                try:
                    await self._call("rois.system.disconnect")
                finally:
                    self._connected = False
                    await self._wire.close()
        finally:
            self._disconnecting = None

    async def _call(self, method: str, /, **params: object) -> Any:
        """Run a catalog method.

        Invalid params raise before anything is sent, and a result that does not match the
        catalog raises instead of reaching the caller.

        Returns:
            The result model of the method, which each caller names, because the catalog
            table cannot carry that type.
        """
        if not self._connected:
            raise TransportError(f"Cannot call {method}: client is not connected")
        spec = METHODS_BY_NAME[method]
        request = spec.params.model_validate(params)
        raw = await self._wire.send(method, request.model_dump(mode="json"))
        result: Any = spec.result.model_validate(raw)
        if result.return_code != ReturnCode.OK:
            raise RoISError(result.return_code, method)
        return result

    def _on_notification(self, notification: JsonRpcNotification) -> None:
        """Validate a catalog notification and emit its params.

        Methods outside the catalog stay on the ``notification`` event of the transport.
        """
        method = notification["method"]
        spec = NOTIFICATIONS_BY_NAME.get(method)
        if spec is None:
            return
        try:
            parsed = spec.params.model_validate(notification.get("params", {}))
        except ValidationError as error:
            fault = TransportError(f"Invalid params in {method} notification: {error}")
            self._emit("error", fault)
            return
        self._emit(method, parsed)

    def _on_close(self, code: int, reason: str) -> None:
        self._connected = False
        self._emit("close", code, reason)

    def _on_error(self, error: Exception) -> None:
        self._emit("error", error)
