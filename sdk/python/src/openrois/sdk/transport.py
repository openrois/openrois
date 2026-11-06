"""WebSocket transport of the OpenRoIS Python client SDK.

Carries the JSON-RPC messages between RoISClient and an engine. It opens and closes the
connection, correlates replies with requests by id, and passes on what the engine pushes.
It does not look inside params or results: RoISClient validates those against the method
catalog of openrois-interfaces.

A reader task receives every message. A plain listener runs inline in that task, in the
order the messages arrived. A coroutine function runs in a task of its own, because a
listener that awaited a request inline would wait for a reply only the reader can deliver.

Usage:
    transport = WebSocketTransport()
    await transport.connect("ws://127.0.0.1:8765")
    result = await transport.send("rois.command.search", {"condition": ""})
    await transport.close()

Architecture: docs/architecture.md section 5 (Client & Service Application SDK)
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from enum import StrEnum
from functools import partial
from typing import Any, Literal, NotRequired, Self, TypedDict, overload

from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as open_socket
from websockets.exceptions import ConnectionClosed, WebSocketException

from openrois.sdk.errors import RequestTimeoutError, RoISConnectionError, RpcError, TransportError

logger = logging.getLogger(__name__)

type Listener[*Args] = Callable[[*Args], object]

#: The only valid JSON-RPC version string.
JSONRPC_VERSION = "2.0"

#: The seconds a request waits for its reply.
DEFAULT_REQUEST_TIMEOUT = 30.0

#: The seconds the WebSocket has to open.
DEFAULT_CONNECT_TIMEOUT = 10.0

#: The largest message accepted, in bytes. The websockets default of 1 MiB would close the
#: connection on a large get_profile, where a browser has no such limit.
MAX_MESSAGE_SIZE = 16 * 2**20

#: The close code reported when the connection ended with no close frame.
ABNORMAL_CLOSE = 1006

#: The most bytes of UTF-8 that a close frame has room for as its reason.
MAX_CLOSE_REASON_BYTES = 123

#: The shortest method name a notification can have, as in the TypeScript client.
MIN_METHOD_LENGTH = 3

#: How many cancelled requests a transport remembers. A peer might never answer them, so the
#: memory has to stop somewhere, and a reply past it is only reported as a fault.
MAX_ABANDONED_REQUESTS = 1024

#: How much of an unusable message an error quotes.
_QUOTED_CHARACTERS = 200


class TransportState(StrEnum):
    """Connection lifecycle of a transport.

    DISCONNECTED -> CONNECTING -> CONNECTED -> CLOSING -> DISCONNECTED, and a connection
    that ends on its own goes from CONNECTED straight to DISCONNECTED.
    """

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    CLOSING = "CLOSING"


class JsonRpcNotification(TypedDict):
    """A notification as it arrived, which the ``notification`` event of a transport carries."""

    jsonrpc: str
    method: str
    params: NotRequired[Any]


class Emitter:
    """Base class of whatever emits events.

    A fault is an event that nothing turns into a raise, because the caller of ``_emit`` is
    the reader of a socket and has to carry on with the next message. It goes to the
    ``error`` listeners, or to the log if there are none.

    Subclasses declare ``on`` and ``off``, typed for each of their event names.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., object]]] = {}
        # The event loop keeps only a weak reference to a task, so work that is still running
        # needs this one.
        self._background: set[asyncio.Future[object]] = set()

    def _add_listener(self, name: str, listener: Callable[..., object]) -> Self:
        self._listeners.setdefault(name, []).append(listener)
        return self

    def _remove_listener(self, name: str, listener: Callable[..., object]) -> Self:
        added = self._listeners.get(name, [])
        for index in range(len(added) - 1, -1, -1):
            # By equality, since each read of a bound method gives a new object.
            if added[index] == listener:
                del added[index]
                break
        return self

    def _emit(self, name: str, *args: object) -> None:
        """Call the listeners of an event, and report what they raise as a fault."""
        # A copy, so a listener can remove itself without skipping the next one.
        listeners = list(self._listeners.get(name, ()))
        if name == "error" and not listeners:
            _log_fault(args[0])
        for listener in listeners:
            try:
                returned = listener(*args)
            # A CancelledError here is one the listener raised itself, since nothing in this
            # method awaits, and a reader that let it through would stop for good.
            except (Exception, asyncio.CancelledError) as fault:
                self._report_fault(name, fault)
                continue
            if inspect.isawaitable(returned):
                self._run_aside(name, returned)

    def _run_aside(self, name: str, work: Awaitable[object]) -> None:
        """Run work in a task of its own, and report what it raises as a fault of an event."""
        task = asyncio.ensure_future(work)
        self._background.add(task)
        task.add_done_callback(partial(self._settle, name))

    def _settle(self, name: str, task: asyncio.Future[object]) -> None:
        """Report what work that ran in its own task raised."""
        self._background.discard(task)
        if not task.cancelled() and (fault := task.exception()) is not None:
            self._report_fault(name, fault)

    def _report_fault(self, name: str, fault: BaseException) -> None:
        """Pass on what a listener raised. An ``error`` listener that raises can only be logged."""
        if name == "error":
            _log_fault(fault)
            return
        self._emit("error", fault if isinstance(fault, Exception) else TransportError(repr(fault)))


def _log_fault(fault: object) -> None:
    """Log a fault that has nowhere else to go, with its traceback when it has one."""
    logger.error(
        "OpenRoIS: %s", fault, exc_info=fault if isinstance(fault, BaseException) else None
    )


def _is_id(value: object) -> bool:
    """Whether a value can be a JSON-RPC id, which excludes the booleans ``int`` includes."""
    return value is None or (isinstance(value, str | int | float) and not isinstance(value, bool))


def _is_error_object(value: object) -> bool:
    """Whether a value has the shape of a JSON-RPC error object."""
    return (
        isinstance(value, dict)
        and value.keys() <= {"code", "message", "data"}
        and type(value.get("code")) is int
        and isinstance(value.get("message"), str)
    )


def _no_constant(name: str) -> object:
    """Refuse NaN and Infinity, which ``json.loads`` accepts although JSON has no such thing."""
    raise ValueError(f"{name} is not JSON")


def _close_outcome(socket: ClientConnection) -> tuple[int, str]:
    """The code and reason a connection ended with.

    A failure this client detected itself, such as a message over ``MAX_MESSAGE_SIZE``, ends in
    a close frame this client sent, because websockets discards what the peer sends after that.
    Read from the protocol, because websockets 14 has no such properties on the connection.
    """
    frame = socket.protocol.close_rcvd or socket.protocol.close_sent
    return (ABNORMAL_CLOSE, "") if frame is None else (int(frame.code), frame.reason)


def _quoted(raw: str | bytes) -> str:
    """The start of a raw message, for an error to quote."""
    return str(raw[:_QUOTED_CHARACTERS])


class WebSocketTransport(Emitter):
    """A single WebSocket connection to an engine, speaking JSON-RPC 2.0.

    One transport manages one connection at a time. After it closes, ``connect`` opens a
    new one.

    Events, for ``on`` and ``off``:

        open          No arguments. The connection opened.
        notification  A JsonRpcNotification arrived, in or outside the catalog.
        close         (code, reason). The connection closed, from either side.
        error         (exception). A message could not be used, or a listener raised.
    """

    def __init__(
        self,
        *,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    ) -> None:
        """Initialize the transport.

        Args:
            request_timeout: The seconds a request waits for its reply.
            connect_timeout: The seconds the WebSocket has to open.
        """
        super().__init__()
        self._request_timeout = request_timeout
        self._connect_timeout = connect_timeout
        self._state = TransportState.DISCONNECTED
        self._url = ""
        self._socket: ClientConnection | None = None
        self._reader: asyncio.Task[None] | None = None
        self._opening: asyncio.Timeout | None = None
        self._connect_ended: asyncio.Event | None = None
        self._close_request: tuple[int, str] | None = None
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._abandoned: deque[str] = deque(maxlen=MAX_ABANDONED_REQUESTS)
        self._next_id = 1

    @property
    def state(self) -> TransportState:
        """The current connection state."""
        return self._state

    @overload
    def on(self, name: Literal["open"], listener: Listener[()]) -> Self: ...
    @overload
    def on(
        self, name: Literal["notification"], listener: Listener[JsonRpcNotification]
    ) -> Self: ...
    @overload
    def on(self, name: Literal["close"], listener: Listener[int, str]) -> Self: ...
    @overload
    def on(self, name: Literal["error"], listener: Listener[Exception]) -> Self: ...
    def on(self, name: str, listener: Callable[..., object]) -> Self:
        """Add a listener. It stays until ``off`` removes it."""
        return self._add_listener(name, listener)

    @overload
    def off(self, name: Literal["open"], listener: Listener[()]) -> Self: ...
    @overload
    def off(
        self, name: Literal["notification"], listener: Listener[JsonRpcNotification]
    ) -> Self: ...
    @overload
    def off(self, name: Literal["close"], listener: Listener[int, str]) -> Self: ...
    @overload
    def off(self, name: Literal["error"], listener: Listener[Exception]) -> Self: ...
    def off(self, name: str, listener: Callable[..., object]) -> Self:
        """Remove a listener added with ``on``."""
        return self._remove_listener(name, listener)

    async def connect(self, url: str) -> None:
        """Open a WebSocket connection to an engine.

        Args:
            url: The WebSocket URL, for example ``ws://127.0.0.1:8765``.

        Raises:
            RoISConnectionError: The connection failed or timed out, ``close`` ran first, or
                this transport is not disconnected.
        """
        if self._state is not TransportState.DISCONNECTED:
            raise RoISConnectionError(f"Cannot connect: transport is in state {self._state}", url)
        self._url = url
        self._state = TransportState.CONNECTING
        ended = self._connect_ended = asyncio.Event()
        try:
            # asyncio.timeout rather than open_timeout, because it gives close() something
            # to end the attempt with. Everything here runs in the caller's task, so a
            # cancellation reaches the handshake too, and websockets drops the socket.
            async with asyncio.timeout(self._connect_timeout) as self._opening:
                socket = await open_socket(url, open_timeout=None, max_size=MAX_MESSAGE_SIZE)
        except TimeoutError as error:
            closed_first = self._state is TransportState.CLOSING
            message = (
                "Connection closed by client"
                if closed_first
                else f"Connection timed out after {self._connect_timeout}s"
            )
            raise RoISConnectionError(message, url) from error
        except (OSError, WebSocketException, ValueError) as error:
            raise RoISConnectionError(f"WebSocket connection failed: {error}", url) from error
        else:
            if self._state is TransportState.CLOSING:
                # close() ran after the handshake had ended, too late to stop it. Set aside,
                # because close() is waiting for this attempt to end.
                self._run_aside("close", socket.close(1000, "client closed"))
                raise RoISConnectionError("Connection closed by client", url)
            self._socket = socket
            self._state = TransportState.CONNECTED
            self._reader = asyncio.create_task(self._read(socket))
        finally:
            self._opening = None
            self._connect_ended = None
            if self._state is not TransportState.CONNECTED:
                self._state = TransportState.DISCONNECTED
            ended.set()
        self._emit("open")

    async def send(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        """Send a JSON-RPC request and wait for its reply.

        Nothing is validated here. RoISClient checks results against the method catalog, and
        methods outside the catalog have nothing to check against.

        Args:
            method: The JSON-RPC method name, for example ``rois.command.search``.
            params: The named parameters of the method.

        Returns:
            The ``result`` of the reply.

        Raises:
            RpcError: The engine answered with a JSON-RPC error.
            RequestTimeoutError: No reply arrived within the request timeout.
            RoISConnectionError: The connection closed while waiting.
            TransportError: The transport is not connected.
        """
        socket = self._socket
        if self._state is not TransportState.CONNECTED or socket is None:
            raise TransportError(f"Cannot send: transport is in state {self._state}")

        request_id = f"req-{self._next_id}"
        self._next_id += 1
        request: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "id": request_id, "method": method}
        if params is not None:
            request["params"] = params
        message = json.dumps(request)

        # Registered first, because the reply can arrive while send() is still draining.
        reply = asyncio.get_running_loop().create_future()
        self._pending[request_id] = reply
        try:
            async with asyncio.timeout(self._request_timeout):
                await socket.send(message)
                return await reply
        except TimeoutError as error:
            raise RequestTimeoutError(method, request_id, self._request_timeout) from error
        except ConnectionClosed as error:
            raise RoISConnectionError(f"Connection lost: {error}", self._url) from error
        except asyncio.CancelledError:
            # The peer does not know the caller left, so a reply can still arrive.
            if request_id in self._pending:
                self._abandoned.append(request_id)
            raise
        finally:
            self._pending.pop(request_id, None)
            # The end of the connection can fail the reply of a request that left through
            # another branch. The caller has its error, so asyncio must not log this one.
            if reply.done() and not reply.cancelled():
                reply.exception()

    async def close(self, code: int = 1000, reason: str = "client closed") -> None:
        """Close the connection, and wait until it has closed.

        Requests still waiting fail with RoISConnectionError. This is safe to call when
        already disconnected, and calls that overlap all wait for the same close. A caller who
        is cancelled stops waiting, and the close goes on without it.

        During ``connect`` it ends the attempt instead and waits for it: ``connect`` raises
        RoISConnectionError, and no ``close`` event fires, because no connection opened.

        Args:
            code: The WebSocket close code: 1000, or 3000 to 4999, which is what the
                WebSocket API lets a client send.
            reason: The close reason, at most 123 bytes of UTF-8.

        Raises:
            TransportError: The code or the reason is not one of those, in any state. A
                connection stays open.
        """
        if code != 1000 and not 3000 <= code <= 4999:
            raise TransportError(f"Cannot close with code {code}: use 1000, or 3000 to 4999")
        if len(reason.encode()) > MAX_CLOSE_REASON_BYTES:
            raise TransportError(
                f"Cannot close with this reason: it is over {MAX_CLOSE_REASON_BYTES} "
                "bytes of UTF-8"
            )

        attempt = self._connect_ended
        if attempt is not None:
            self._abort_connect()
            await attempt.wait()
            return

        self._start_close(code, reason)
        if self._reader is not None:
            # With wait, and not by awaiting the task, for two reasons. A caller who gives up
            # must not cancel the reader, and the end of a cancelled reader is not a
            # cancellation of this caller.
            await asyncio.wait([self._reader])

    def _start_close(self, code: int = 1000, reason: str = "client closed") -> None:
        """Begin to close a connection, and leave the rest to the transport.

        Does nothing unless connected. The closing handshake runs apart from any caller, because
        it can take as long as the close timeout of websockets, and only its end aborts a peer
        that never answers. A caller who was cancelled during it would leave that peer open.
        """
        socket = self._socket
        if self._state is not TransportState.CONNECTED or socket is None:
            return
        self._state = TransportState.CLOSING
        self._close_request = (code, reason)
        self._fail_pending("Connection closed by client")
        self._run_aside("close", socket.close(code, reason))

    def _abort_connect(self) -> None:
        """End the connect in progress by expiring its timeout at once."""
        opening = self._opening
        self._state = TransportState.CLOSING
        # A timeout that has already expired is ending the attempt by itself, and it refuses
        # to be rescheduled.
        if opening is not None and not opening.expired():
            opening.reschedule(asyncio.get_running_loop().time())

    # -----------------------------------------------------------------------
    # Private: the reader
    # -----------------------------------------------------------------------

    async def _read(self, socket: ClientConnection) -> None:
        """Receive every message of a connection, then report how it ended.

        The report runs however this ends. Cancelling every task is how a program commonly shuts
        down, and without it the requests would wait for a reply nothing can deliver.
        """
        try:
            # The close code says how the connection ended, whichever way this loop stops.
            with suppress(ConnectionClosed):
                async for raw in socket:
                    # After close() nothing reaches a listener, because the caller has been told
                    # the connection is gone, but the socket still has to drain to finish closing.
                    if self._state is TransportState.CONNECTED:
                        self._receive(raw)
            await socket.wait_closed()
        except BaseException:
            # Nothing will read this connection again, so nothing may leave it open.
            socket.transport.abort()
            raise
        finally:
            self._finish(*_close_outcome(socket))

    def _finish(self, code: int, reason: str) -> None:
        """Fail what still waits, and tell the listeners the connection has closed."""
        if self._close_request is not None:
            # Report what the caller of close() asked for, because a peer that never answers
            # the close frame leaves only 1006 behind.
            code, reason = self._close_request
            self._close_request = None
        self._fail_pending(
            f"WebSocket closed unexpectedly: code {code}, reason: {reason or 'none'}"
        )
        self._socket = None
        self._reader = None
        self._state = TransportState.DISCONNECTED
        self._emit("close", code, reason)

    def _fail_pending(self, message: str) -> None:
        """Fail every request still waiting, so that none hangs until its timeout."""
        for reply in self._pending.values():
            if not reply.done():
                reply.set_exception(RoISConnectionError(message, self._url))
        self._pending.clear()

    def _receive(self, raw: str | bytes) -> None:
        """Classify one message by its fields and dispatch it, or report it as a fault."""
        if isinstance(raw, bytes):
            # JSON-RPC here is text, and a browser could not parse this frame at all.
            self._emit("error", TransportError(f"Received a binary message: {_quoted(raw)}"))
            return
        try:
            message = json.loads(raw, parse_constant=_no_constant)
        except (ValueError, RecursionError):
            self._emit("error", TransportError(f"Received malformed JSON: {_quoted(raw)}"))
            return
        if not isinstance(message, dict):
            self._emit("error", TransportError(f"Received non-object JSON: {_quoted(raw)}"))
            return

        fields = message.keys()
        versioned = message.get("jsonrpc") == JSONRPC_VERSION
        has_id = _is_id(message.get("id"))
        if versioned and has_id and fields == {"jsonrpc", "id", "result"}:
            self._settle_request(message["id"], message["result"], None)
        elif (
            versioned
            and has_id
            and fields == {"jsonrpc", "id", "error"}
            and _is_error_object(message["error"])
        ):
            error = message["error"]
            fault = RpcError(error["code"], error["message"], error.get("data"))
            self._settle_request(message["id"], None, fault)
        elif (
            versioned
            and fields <= {"jsonrpc", "method", "params"}
            and isinstance(message.get("method"), str)
            and len(message["method"]) >= MIN_METHOD_LENGTH
            and isinstance(message.get("params", {}), dict | list)
        ):
            # Only ever under this one name, because a server could otherwise fake the
            # close event by naming a notification after it.
            self._emit("notification", message)
        else:
            self._emit("error", TransportError(f"Received unrecognized message: {_quoted(raw)}"))

    def _settle_request(self, request_id: object, result: Any, fault: RpcError | None) -> None:
        """Hand a reply to the request it answers."""
        reply = self._pending.pop(request_id, None) if isinstance(request_id, str) else None
        if reply is None and request_id in self._abandoned:
            # A caller who cancels stops caring about the answer, so this is no fault. It is the
            # same event as the reply.done() branch below, some ticks later.
            pass
        elif reply is None:
            # A duplicate, or a reply that arrived after its request timed out.
            self._emit("error", TransportError(f"Received reply for unknown id: {request_id!r}"))
        elif reply.done():
            # The caller was cancelled and has not yet run far enough to remove the request.
            pass
        elif fault is not None:
            reply.set_exception(fault)
        else:
            reply.set_result(result)
