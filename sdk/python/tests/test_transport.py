"""The client against servers that misbehave on cue: correlation, timeouts and faults.

Most tests connect to testing/conformance/scripted_server.py, which every SDK shares. A path
of that server picks a script, and ``/reverse`` holds a lone request forever, which is what a
timeout needs. It never sends a JSON-RPC error, a notification or a bad result, so the tests
of those run a small server in this process, where a handler decides each answer.
"""

from __future__ import annotations

import asyncio
import gc
import inspect
import json
import logging
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial
from types import MappingProxyType
from typing import Any, Final

import pytest
from openrois.interfaces import CompletedParams, ReturnCode
from pydantic import ValidationError
from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as open_socket
from websockets.asyncio.server import ServerConnection, serve

from openrois.sdk import (
    RequestTimeoutError,
    RoISClient,
    RoISConnectionError,
    RoISError,
    RpcError,
    TransportError,
)
from openrois.sdk.transport import (
    MAX_MESSAGE_SIZE,
    JsonRpcNotification,
    TransportState,
    WebSocketTransport,
)

SEARCH = "rois.command.search"
COMPLETED: Final = "rois.command.completed"

#: How long a test waits for something that should happen at once.
PROMPTLY = 5.0

type Message = dict[str, Any]
type Handler = Callable[[ServerConnection], Awaitable[None]]


@asynccontextmanager
async def serving(handler: Handler, **options: Any) -> AsyncIterator[str]:
    """Run a server in this process, and give its URL."""
    async with serve(handler, "127.0.0.1", 0, max_size=None, **options) as server:
        yield f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


@asynccontextmanager
async def mute() -> AsyncIterator[str]:
    """A server that accepts a connection and never answers its handshake."""

    async def wait(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read()
        writer.close()

    async with await asyncio.start_server(wait, "127.0.0.1", 0) as server:
        yield f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


@asynccontextmanager
async def deaf() -> AsyncIterator[tuple[str, list[ServerConnection]]]:
    """A server that completes the handshake and then reads nothing, not even a close frame.

    It compresses nothing either, so that what a client sends fills the socket.

    Yields:
        The URL, and the list that receives each connection as it opens.
    """
    connections: list[ServerConnection] = []

    async def handle(connection: ServerConnection) -> None:
        connection.transport.pause_reading()
        connections.append(connection)
        await connection.wait_closed()

    async with serving(handle, compression=None) as url:
        try:
            yield url, connections
        finally:
            # It would never notice that a client left, and the server waits for its handlers.
            for connection in connections:
                connection.transport.abort()


def reply(request: Message, **result: object) -> str:
    """A reply to a request, with OK unless the caller gives another return code."""
    return json.dumps(
        {"jsonrpc": "2.0", "id": request["id"], "result": {"return_code": "OK", **result}}
    )


def notification(method: str, params: object) -> str:
    return json.dumps({"jsonrpc": "2.0", "method": method, "params": params})


@asynccontextmanager
async def engine(
    answers: dict[str, Callable[[Message], str]] | None = None,
    pushes: tuple[str, ...] = (),
) -> AsyncIterator[tuple[str, list[Message]]]:
    """A server that answers a session as an engine does, and records every request.

    Args:
        answers: The reply of each method that needs more than OK.
        pushes: Messages to send right after the reply to rois.system.connect.

    Yields:
        The URL, and the list that receives each request as it arrives.
    """
    received: list[Message] = []
    known = answers or {}

    async def handle(connection: ServerConnection) -> None:
        async for raw in connection:
            request: Message = json.loads(raw)
            received.append(request)
            answer = known.get(request["method"], reply)
            await connection.send(answer(request))
            if request["method"] == "rois.system.connect":
                for message in pushes:
                    await connection.send(message)

    async with serving(handle) as url:
        yield url, received


class Faults:
    """Records what reaches a listener of ``error``, and lets a test wait for it."""

    def __init__(self) -> None:
        self.seen: list[Exception] = []
        self.arrived = asyncio.Event()

    def __call__(self, error: Exception) -> None:
        self.seen.append(error)
        self.arrived.set()

    async def first(self) -> Exception:
        await asyncio.wait_for(self.arrived.wait(), PROMPTLY)
        return self.seen[0]


def write_out(connection: ServerConnection) -> None:
    """Write what the protocol of a connection has queued, in one write."""
    connection.transport.write(b"".join(connection.protocol.data_to_send()))


def write_at_once(connection: ServerConnection, *messages: str | bytes) -> None:
    """Send text frames in one write, so that a reader gets them all without yielding."""
    for message in messages:
        connection.protocol.send_text(message.encode() if isinstance(message, str) else message)
    write_out(connection)


def close_of(emitter: WebSocketTransport | RoISClient) -> asyncio.Future[tuple[int, str]]:
    """What an emitter reports when its connection closes."""
    closed: asyncio.Future[tuple[int, str]] = asyncio.get_running_loop().create_future()
    emitter.on("close", lambda code, reason: closed.set_result((code, reason)))
    return closed


def free_port() -> int:
    """A port with nothing listening on it."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


async def connected(url: str, **options: float) -> WebSocketTransport:
    transport = WebSocketTransport(**options)
    await transport.connect(url)
    return transport


@pytest.fixture
def quick_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shorten the wait for the close frame of a peer, which is 10 seconds in websockets."""
    quick = partial(open_socket, close_timeout=0.05)
    monkeypatch.setattr("openrois.sdk.transport.open_socket", quick)


class TestErrors:
    def test_the_transport_errors_share_a_base(self) -> None:
        for error in (
            RoISConnectionError("lost"),
            RequestTimeoutError("m", "req-1", 1.0),
            RpcError(-32601, "no"),
        ):
            assert isinstance(error, TransportError)

    def test_connection_errors_keep_except_connection_error_working(self) -> None:
        error = RoISConnectionError("lost", "ws://here")
        assert isinstance(error, ConnectionError)
        assert str(error) == "lost"
        assert error.url == "ws://here"

    def test_timeouts_keep_except_timeout_error_working(self) -> None:
        error = RequestTimeoutError("m", "req-1", 1.5)
        assert isinstance(error, TimeoutError)
        assert (error.method, error.request_id) == ("m", "req-1")
        assert "1.5s" in str(error)

    def test_rpc_errors_carry_code_and_data(self) -> None:
        error = RpcError(-32602, "bad", {"field": "x"})
        assert (error.code, error.data) == (-32602, {"field": "x"})
        assert str(error) == "RPC error -32602: bad"

    def test_rois_errors_carry_the_return_code_and_the_method(self) -> None:
        error = RoISError(ReturnCode.OUT_OF_RESOURCES, "rois.command.bind")
        assert error.return_code == "OUT_OF_RESOURCES"
        assert error.method == "rois.command.bind"


class TestCorrelation:
    async def test_replies_in_reverse_order_reach_their_callers(self, scripted_url: str) -> None:
        transport = await connected(f"{scripted_url}/reverse")
        answered: list[str] = []

        async def ask(condition: str) -> object:
            result = await transport.send(SEARCH, {"condition": condition})
            answered.append(condition)
            return result["component_ref_list"]

        replies = await asyncio.gather(ask("one"), ask("two"), ask("three"))

        assert list(replies) == [["one"], ["two"], ["three"]]
        assert answered == ["three", "two", "one"]
        await transport.close()

    async def test_a_method_with_no_params_sends_none(self) -> None:
        async with engine() as (url, received):
            transport = await connected(url)
            await transport.send("vendor.ping")
            await transport.close()
        assert "params" not in received[0]

    async def test_a_reply_nobody_waits_for_is_a_fault(self) -> None:
        async def twice(connection: ServerConnection) -> None:
            async for raw in connection:
                request = json.loads(raw)
                await connection.send(reply(request))
                await connection.send(reply(request))

        async with serving(twice) as url:
            transport = await connected(url)
            faults = Faults()
            transport.on("error", faults)
            await transport.send("vendor.ping")
            assert "unknown id" in str(await faults.first())
            await transport.close()

    async def test_a_jsonrpc_error_reaches_its_caller_as_rpc_error(self) -> None:
        def refuse(request: Message) -> str:
            error = {"code": -32601, "message": "No such method", "data": ["x"]}
            return json.dumps({"jsonrpc": "2.0", "id": request["id"], "error": error})

        async with engine({"vendor.ping": refuse}) as (url, _):
            transport = await connected(url)
            with pytest.raises(RpcError) as caught:
                await transport.send("vendor.ping")
            assert (caught.value.code, caught.value.data) == (-32601, ["x"])
            await transport.close()

    async def test_a_reply_in_the_tick_of_its_cancellation_leaves_the_reader_working(
        self,
    ) -> None:
        async def together(connection: ServerConnection) -> None:
            async for raw in connection:
                request = json.loads(raw)
                if request["method"] == "vendor.cancelled":
                    write_at_once(connection, notification("vendor.one", {}), reply(request))
                else:
                    await connection.send(reply(request))

        async with serving(together) as url:
            transport = await connected(url)
            faults = Faults()
            transport.on("error", faults)
            waiting = asyncio.create_task(transport.send("vendor.cancelled"))
            # The reader runs this and then reaches the reply, with no chance for the caller to
            # run in between and take its request away.
            transport.on("notification", lambda _: waiting.cancel())

            with pytest.raises(asyncio.CancelledError):
                await waiting

            assert await transport.send("vendor.ping") == {"return_code": "OK"}
            assert faults.seen == []
            await transport.close()

    async def test_a_reply_to_a_cancelled_request_is_no_fault(self) -> None:
        async def late(connection: ServerConnection) -> None:
            async for raw in connection:
                await asyncio.sleep(0.03)
                await connection.send(reply(json.loads(raw)))

        async with serving(late) as url:
            transport = await connected(url)
            faults = Faults()
            transport.on("error", faults)

            with pytest.raises(TimeoutError):
                await asyncio.wait_for(transport.send("vendor.ping"), 0.01)

            # The server answers in order, so this reply comes after the one nobody awaits.
            assert await transport.send("vendor.ping") == {"return_code": "OK"}
            assert faults.seen == []
            await transport.close()

    async def test_the_memory_of_cancelled_requests_is_bounded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("openrois.sdk.transport.MAX_ABANDONED_REQUESTS", 2)
        requests: asyncio.Queue[Message] = asyncio.Queue()

        async def hold(connection: ServerConnection) -> None:
            async for raw in connection:
                request = json.loads(raw)
                if request["method"] == "vendor.flush":
                    while not requests.empty():
                        await connection.send(reply(requests.get_nowait()))
                    await connection.send(reply(request))
                else:
                    requests.put_nowait(request)

        async with serving(hold) as url:
            transport = await connected(url)
            faults = Faults()
            transport.on("error", faults)
            for _ in range(3):
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(transport.send("vendor.ping"), 0.01)

            await transport.send("vendor.flush")

            assert [str(fault) for fault in faults.seen] == [
                "Received reply for unknown id: 'req-1'"
            ]
            await transport.close()

    async def test_a_message_over_the_websockets_default_limit_arrives(self) -> None:
        size = 2 * 2**20
        assert size < MAX_MESSAGE_SIZE

        async with engine({"vendor.big": lambda r: reply(r, blob="x" * size)}) as (url, _):
            transport = await connected(url)
            result = await transport.send("vendor.big")
            assert len(result["blob"]) == size
            await transport.close()


class TestTimeouts:
    @pytest.mark.parametrize("opens", [WebSocketTransport, RoISClient.connect])
    def test_the_defaults_are_those_of_every_sdk(self, opens: Callable[..., object]) -> None:
        options = inspect.signature(opens).parameters
        assert options["request_timeout"].default == 30.0
        assert options["connect_timeout"].default == 10.0

    async def test_a_request_with_no_reply_times_out(self, scripted_url: str) -> None:
        transport = await connected(f"{scripted_url}/reverse", request_timeout=0.05)

        with pytest.raises(RequestTimeoutError) as caught:
            await transport.send(SEARCH, {"condition": "alone"})

        assert caught.value.method == SEARCH
        assert caught.value.request_id == "req-1"
        assert transport.state is TransportState.CONNECTED
        await transport.close()

    async def test_except_timeout_error_catches_it(self, scripted_url: str) -> None:
        transport = await connected(f"{scripted_url}/reverse", request_timeout=0.05)
        with pytest.raises(TimeoutError):
            await transport.send(SEARCH, {"condition": "alone"})
        await transport.close()

    async def test_a_reply_after_the_timeout_is_a_fault(self) -> None:
        async def late(connection: ServerConnection) -> None:
            async for raw in connection:
                await asyncio.sleep(0.1)
                await connection.send(reply(json.loads(raw)))

        async with serving(late) as url:
            transport = await connected(url, request_timeout=0.02)
            faults = Faults()
            transport.on("error", faults)
            with pytest.raises(RequestTimeoutError):
                await transport.send("vendor.ping")
            assert "unknown id" in str(await faults.first())
            await transport.close()

    async def test_a_server_that_never_answers_the_handshake_times_out(self) -> None:
        async with mute() as url:
            transport = WebSocketTransport(connect_timeout=0.05)

            with pytest.raises(RoISConnectionError, match="timed out") as caught:
                await transport.connect(url)

            assert caught.value.url == url
            assert transport.state is TransportState.DISCONNECTED

    async def test_a_cancelled_request_leaves_the_transport_working(
        self, scripted_url: str
    ) -> None:
        transport = await connected(f"{scripted_url}/reverse")
        waiting = asyncio.create_task(transport.send(SEARCH, {"condition": "alone"}))
        await asyncio.sleep(0.01)

        waiting.cancel()

        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert transport.state is TransportState.CONNECTED
        await transport.close()


class TestConnecting:
    async def test_nothing_listening_fails_with_a_connection_error(self) -> None:
        url = f"ws://127.0.0.1:{free_port()}"
        transport = WebSocketTransport()

        with pytest.raises(RoISConnectionError) as caught:
            await transport.connect(url)

        assert isinstance(caught.value, ConnectionError)
        assert caught.value.url == url
        assert transport.state is TransportState.DISCONNECTED

    async def test_a_refused_handshake_fails_with_a_connection_error(
        self, scripted_url: str
    ) -> None:
        with pytest.raises(RoISConnectionError, match="404"):
            await WebSocketTransport().connect(f"{scripted_url}/no-such-script")

    @pytest.mark.parametrize("url", ["http://127.0.0.1:1", "not a url", "ws://127.0.0.1:99999"])
    async def test_a_bad_url_fails_with_a_connection_error(self, url: str) -> None:
        with pytest.raises(RoISConnectionError):
            await WebSocketTransport().connect(url)

    async def test_connecting_twice_fails_and_keeps_the_connection(
        self, scripted_url: str
    ) -> None:
        transport = await connected(f"{scripted_url}/malformed")
        with pytest.raises(RoISConnectionError, match="CONNECTED"):
            await transport.connect(f"{scripted_url}/malformed")
        assert transport.state is TransportState.CONNECTED
        await transport.close()

    async def test_close_during_connect_ends_the_attempt_with_no_close_event(self) -> None:
        async with mute() as url:
            transport = WebSocketTransport()
            closed: list[int] = []
            transport.on("close", lambda code, _: closed.append(code))
            attempt = asyncio.create_task(transport.connect(url))
            await asyncio.sleep(0.01)
            assert transport.state.value == "CONNECTING"

            await asyncio.wait_for(transport.close(), PROMPTLY)

            with pytest.raises(RoISConnectionError, match="closed by client"):
                await asyncio.wait_for(attempt, PROMPTLY)
            assert transport.state is TransportState.DISCONNECTED
            assert closed == []

    async def test_close_just_after_the_handshake_still_ends_the_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transport = WebSocketTransport()
        closes: list[asyncio.Task[None]] = []
        ended = asyncio.Event()

        async def hold(connection: ServerConnection) -> None:
            await connection.wait_closed()
            ended.set()

        async def handshake_ends_first(*args: Any, **options: Any) -> ClientConnection:
            socket = await open_socket(*args, **options)
            closes.append(asyncio.create_task(transport.close()))
            await asyncio.sleep(0)
            return socket

        monkeypatch.setattr("openrois.sdk.transport.open_socket", handshake_ends_first)

        async with serving(hold) as url:
            with pytest.raises(RoISConnectionError, match="closed by client"):
                await transport.connect(url)

            assert transport.state is TransportState.DISCONNECTED
            await asyncio.wait_for(closes[0], PROMPTLY)
            await asyncio.wait_for(ended.wait(), PROMPTLY)

    async def test_close_during_connect_returns_with_the_attempt_over(
        self, scripted_url: str
    ) -> None:
        async with mute() as url:
            transport = WebSocketTransport()
            attempt = asyncio.create_task(transport.connect(url))
            await asyncio.sleep(0.01)

            await asyncio.wait_for(transport.close(), PROMPTLY)

            assert transport.state is TransportState.DISCONNECTED
            await transport.connect(f"{scripted_url}/malformed")
            await transport.close()
            with pytest.raises(RoISConnectionError, match="closed by client"):
                await attempt

    async def test_a_cancelled_connect_leaves_the_transport_disconnected(self) -> None:
        async with mute() as url:
            transport = WebSocketTransport()
            attempt = asyncio.create_task(transport.connect(url))
            await asyncio.sleep(0.01)

            attempt.cancel()

            with pytest.raises(asyncio.CancelledError):
                await attempt
            assert transport.state is TransportState.DISCONNECTED

    async def test_open_fires_when_the_connection_opens(self, scripted_url: str) -> None:
        transport = WebSocketTransport()
        opened: list[bool] = []
        transport.on("open", lambda: opened.append(True))
        await transport.connect(f"{scripted_url}/malformed")
        assert opened == [True]
        await transport.close()


class TestFaults:
    async def test_a_malformed_message_reaches_the_error_listener(self, scripted_url: str) -> None:
        transport = await connected(f"{scripted_url}/malformed")
        faults = Faults()
        transport.on("error", faults)

        first = await transport.send(SEARCH, {"condition": "before"})

        assert first["component_ref_list"] == ["before"]
        assert len(faults.seen) == 2
        assert all(isinstance(fault, TransportError) for fault in faults.seen)
        second = await transport.send(SEARCH, {"condition": "after"})
        assert second["component_ref_list"] == ["after"]
        await transport.close()

    async def test_with_no_error_listener_a_fault_is_logged(
        self, scripted_url: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        transport = await connected(f"{scripted_url}/malformed")

        with caplog.at_level(logging.ERROR, logger="openrois.sdk"):
            await transport.send(SEARCH, {"condition": "before"})

        assert sum("OpenRoIS" in record.getMessage() for record in caplog.records) == 2
        await transport.close()

    @pytest.mark.parametrize(
        "message",
        [
            "[1, 2]",
            '"text"',
            "null",
            b"\xff\xfe\x00",
            "[" * 200_000,
            '{"jsonrpc": "1.0", "id": "req-1", "result": {}}',
            '{"id": "req-1", "result": {}}',
            '{"jsonrpc": "2.0", "id": true, "result": {}}',
            '{"jsonrpc": "2.0", "id": ["req-1"], "result": {}}',
            '{"jsonrpc": "2.0", "id": "req-1", "result": {}, "extra": 1}',
            '{"jsonrpc": "2.0", "id": "req-1", "error": "text"}',
            '{"jsonrpc": "2.0", "id": "req-1", "error": {"code": "x", "message": "m"}}',
            '{"jsonrpc": "2.0", "id": "req-1", "error": {"code": 1}}',
            '{"jsonrpc": "2.0", "id": "req-1", "method": "server.request"}',
            '{"jsonrpc": "2.0", "method": 7}',
            '{"jsonrpc": "2.0", "method": "m.m", "params": 7}',
            '{"jsonrpc": "2.0", "method": "ab"}',
            '{"jsonrpc": "2.0", "method": ""}',
            '{"jsonrpc": "2.0", "method": "m.m", "params": {"x": NaN}}',
            '{"jsonrpc": "2.0", "method": "m.m", "params": {"x": -Infinity}}',
            b'{"jsonrpc": "2.0", "method": "m.m", "params": {}}',
        ],
    )
    async def test_an_unusable_message_is_a_fault_and_the_transport_keeps_working(
        self, message: str | bytes
    ) -> None:
        async def garbled(connection: ServerConnection) -> None:
            async for raw in connection:
                await connection.send(message)
                await connection.send(reply(json.loads(raw)))

        async with serving(garbled) as url:
            transport = await connected(url)
            faults = Faults()
            seen: list[JsonRpcNotification] = []
            transport.on("error", faults)
            transport.on("notification", seen.append)

            result = await transport.send("vendor.ping")

            assert result == {"return_code": "OK"}
            assert all(isinstance(fault, TransportError) for fault in faults.seen)
            assert len(faults.seen) == 1
            assert seen == []
            await transport.close()

    async def test_a_message_over_the_limit_says_so_and_is_not_a_dropped_connection(
        self,
    ) -> None:
        over = {"vendor.big": lambda r: reply(r, blob="x" * MAX_MESSAGE_SIZE)}
        async with engine(over) as (url, _):
            transport = await connected(url)
            closed = close_of(transport)

            with pytest.raises(RoISConnectionError, match="code 1009"):
                await transport.send("vendor.big")

            code, reason = await closed
            assert code == 1009
            assert str(MAX_MESSAGE_SIZE) in reason

    async def test_text_that_is_not_utf8_says_so_and_is_not_a_dropped_connection(self) -> None:
        async def garbled(connection: ServerConnection) -> None:
            await connection.recv()
            write_at_once(connection, b"\xff")
            await connection.wait_closed()

        async with serving(garbled) as url:
            transport = await connected(url)
            closed = close_of(transport)

            with pytest.raises(RoISConnectionError, match="code 1007"):
                await transport.send("vendor.ping")

            assert (await closed)[0] == 1007

    async def test_a_send_stuck_when_the_connection_ends_fails_and_logs_nothing(self) -> None:
        unretrieved: list[dict[str, Any]] = []
        asyncio.get_running_loop().set_exception_handler(lambda _, fault: unretrieved.append(fault))

        async with deaf() as (url, connections):
            transport = await connected(url)
            closed = close_of(transport)
            # The kernel would otherwise take all of this, and no send would have to wait.
            assert transport._socket is not None
            sent = transport._socket.transport.get_extra_info("socket")
            sent.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
            sends = [
                asyncio.create_task(transport.send("vendor.ping", {"blob": "x" * 2**23}))
                for _ in range(4)
            ]
            await asyncio.sleep(0.05)

            connections[0].transport.abort()

            calls = await asyncio.gather(*sends, return_exceptions=True)
            await closed

        assert all(isinstance(call, RoISConnectionError) for call in calls)
        assert all("Connection lost" in str(call) for call in calls)
        del calls, sends
        gc.collect()
        assert unretrieved == []

    async def test_a_dropped_connection_fails_pending_requests_and_fires_close(
        self, scripted_url: str
    ) -> None:
        transport = await connected(f"{scripted_url}/drop")
        closed = close_of(transport)

        calls = await asyncio.gather(
            transport.send(SEARCH, {"condition": "one"}),
            transport.send(SEARCH, {"condition": "two"}),
            transport.send(SEARCH, {"condition": "three"}),
            return_exceptions=True,
        )

        assert all(isinstance(call, RoISConnectionError) for call in calls)
        assert (await closed)[0] == 1006
        assert transport.state is TransportState.DISCONNECTED
        with pytest.raises(TransportError, match="DISCONNECTED"):
            await transport.send(SEARCH, {"condition": "after"})

    async def test_a_server_close_reaches_close_with_its_code_and_reason(
        self, scripted_url: str
    ) -> None:
        transport = await connected(f"{scripted_url}/close-1001")
        closed = close_of(transport)

        await transport.send(SEARCH, {"condition": "only"})

        assert await closed == (1001, "scripted close")

    async def test_requests_fail_when_a_server_closes(self, scripted_url: str) -> None:
        transport = await connected(f"{scripted_url}/close-1001", request_timeout=PROMPTLY)
        closed = close_of(transport)
        await transport.send(SEARCH, {"condition": "first"})
        await closed
        with pytest.raises(TransportError):
            await transport.send(SEARCH, {"condition": "second"})


class TestClosing:
    async def test_sending_before_connecting_fails_locally(self) -> None:
        with pytest.raises(TransportError, match="DISCONNECTED"):
            await WebSocketTransport().send("vendor.ping")

    async def test_closing_before_connecting_does_nothing(self) -> None:
        await WebSocketTransport().close()

    async def test_close_reports_the_code_and_reason_it_was_given(self, scripted_url: str) -> None:
        transport = await connected(f"{scripted_url}/malformed")
        closed = close_of(transport)

        await transport.close(4001, "done here")

        assert closed.done()
        assert closed.result() == (4001, "done here")
        assert transport.state is TransportState.DISCONNECTED

    @pytest.mark.usefixtures("quick_close")
    async def test_a_peer_that_ignores_the_close_frame_still_gets_the_code_reported(self) -> None:
        async with deaf() as (url, _):
            transport = await connected(url)
            closed = close_of(transport)

            await transport.close(4001, "done here")

            assert closed.result() == (4001, "done here")
            assert transport.state is TransportState.DISCONNECTED

    async def test_close_reports_what_the_caller_asked_whatever_the_peer_answers(self) -> None:
        closing = asyncio.Event()

        async def crossing(connection: ServerConnection) -> None:
            # Not reading keeps the client's close frame from being echoed, as usual.
            connection.transport.pause_reading()
            await closing.wait()
            connection.protocol.send_close(1001, "going away")
            write_out(connection)
            connection.transport.resume_reading()
            await connection.wait_closed()

        async with serving(crossing) as url:
            transport = await connected(url)
            closed = close_of(transport)
            closes = asyncio.create_task(transport.close(4001, "done here"))
            await asyncio.sleep(0.01)

            closing.set()

            await asyncio.wait_for(closes, PROMPTLY)
            assert closed.result() == (4001, "done here")

    @pytest.mark.usefixtures("quick_close")
    async def test_a_cancelled_close_finishes_without_its_caller(self) -> None:
        async with deaf() as (url, _):
            transport = await connected(url)
            closed = close_of(transport)

            with pytest.raises(TimeoutError):
                await asyncio.wait_for(transport.close(4001, "done here"), 0.01)

            assert await asyncio.wait_for(closed, PROMPTLY) == (4001, "done here")
            assert transport.state is TransportState.DISCONNECTED

    @pytest.mark.usefixtures("quick_close")
    async def test_one_cancelled_close_leaves_another_caller_waiting(self) -> None:
        async with deaf() as (url, _):
            transport = await connected(url)
            closed = close_of(transport)
            first = asyncio.create_task(transport.close())
            second = asyncio.create_task(transport.close())
            await asyncio.sleep(0)

            first.cancel()

            with pytest.raises(asyncio.CancelledError):
                await first
            await asyncio.wait_for(second, PROMPTLY)
            assert closed.done()

    async def test_nothing_reaches_a_listener_after_close(self) -> None:
        closing = asyncio.Event()

        async def late(connection: ServerConnection) -> None:
            # Not reading keeps the close frame from stopping the second message.
            connection.transport.pause_reading()
            await connection.send(notification("vendor.one", {}))
            await closing.wait()
            await connection.send(notification("vendor.two", {}))
            await connection.send("not json")
            connection.transport.resume_reading()
            await connection.wait_closed()

        async with serving(late) as url:
            transport = WebSocketTransport()
            arrived = asyncio.Event()
            seen: list[str] = []
            faults = Faults()

            def record(message: JsonRpcNotification) -> None:
                seen.append(message["method"])
                arrived.set()

            transport.on("error", faults)
            transport.on("notification", record)
            await transport.connect(url)
            await asyncio.wait_for(arrived.wait(), PROMPTLY)

            closes = asyncio.create_task(transport.close())
            await asyncio.sleep(0.01)
            closing.set()
            await asyncio.wait_for(closes, PROMPTLY)

            assert seen == ["vendor.one"]
            assert faults.seen == []

    async def test_a_cancelled_reader_ends_the_connection_and_tells_everyone(self) -> None:
        ended = asyncio.Event()

        async def hold(connection: ServerConnection) -> None:
            await connection.wait_closed()
            ended.set()

        async with serving(hold) as url:
            transport = await connected(url)
            closed = close_of(transport)
            waiting = asyncio.create_task(transport.send("vendor.ping"))
            await asyncio.sleep(0.01)
            assert transport._reader is not None

            transport._reader.cancel()

            assert await asyncio.wait_for(closed, PROMPTLY) == (1006, "")
            with pytest.raises(RoISConnectionError, match="code 1006"):
                await asyncio.wait_for(waiting, PROMPTLY)
            assert transport.state is TransportState.DISCONNECTED
            await asyncio.wait_for(ended.wait(), PROMPTLY)
            await transport.close()
            await transport.connect(url)
            await transport.close()

    async def test_a_reader_cancelled_during_close_is_not_a_cancellation_of_the_caller(
        self,
    ) -> None:
        async with deaf() as (url, _):
            transport = await connected(url)
            closed = close_of(transport)
            closing = asyncio.create_task(transport.close(4001, "done here"))
            await asyncio.sleep(0)
            assert transport._reader is not None

            transport._reader.cancel()

            await asyncio.wait_for(closing, PROMPTLY)
            assert closed.result() == (4001, "done here")

    async def test_close_is_safe_twice_and_overlapping(self, scripted_url: str) -> None:
        transport = await connected(f"{scripted_url}/malformed")
        closes: list[int] = []
        transport.on("close", lambda code, _: closes.append(code))

        await asyncio.gather(transport.close(), transport.close())
        await transport.close()

        assert closes == [1000]

    async def test_close_fails_pending_requests(self, scripted_url: str) -> None:
        transport = await connected(f"{scripted_url}/reverse")
        waiting = asyncio.create_task(transport.send(SEARCH, {"condition": "alone"}))
        await asyncio.sleep(0.01)

        await transport.close()

        with pytest.raises(RoISConnectionError, match="closed by client"):
            await waiting

    @pytest.mark.parametrize("code", [999, 1001, 1006, 2999, 5000])
    async def test_a_code_a_client_cannot_send_is_refused(
        self, scripted_url: str, code: int
    ) -> None:
        transport = await connected(f"{scripted_url}/malformed")
        with pytest.raises(TransportError, match="Cannot close"):
            await transport.close(code)
        assert transport.state is TransportState.CONNECTED
        await transport.close()

    async def test_a_reason_too_long_for_the_frame_is_refused(self, scripted_url: str) -> None:
        transport = await connected(f"{scripted_url}/malformed")
        with pytest.raises(TransportError, match="123 bytes"):
            await transport.close(1000, "é" * 62)
        assert transport.state is TransportState.CONNECTED
        await transport.close(1000, "é" * 61)

    async def test_a_transport_can_connect_again_after_it_closed(self, scripted_url: str) -> None:
        transport = await connected(f"{scripted_url}/malformed")
        await transport.close()
        await transport.connect(f"{scripted_url}/close-1001")
        assert transport.state is TransportState.CONNECTED
        await transport.close()


class TestListeners:
    async def test_a_listener_that_raises_does_not_stop_the_reader_or_the_others(self) -> None:
        pushes = (notification("vendor.one", {}), notification("vendor.two", {}))
        async with engine(pushes=pushes) as (url, _):
            transport = WebSocketTransport()
            seen: list[str] = []
            faults = Faults()

            def bad(message: JsonRpcNotification) -> None:
                raise ValueError(message["method"])

            transport.on("error", faults)
            transport.on("notification", bad)
            transport.on("notification", lambda message: seen.append(message["method"]))
            await transport.connect(url)
            await transport.send("rois.system.connect")
            await faults.first()

            await transport.send("vendor.ping")

            assert seen == ["vendor.one", "vendor.two"]
            assert [str(fault) for fault in faults.seen] == ["vendor.one", "vendor.two"]
            await transport.close()

    async def test_a_listener_that_raises_cancelled_error_does_not_stop_the_reader(self) -> None:
        async with engine(pushes=(notification("vendor.one", {}),)) as (url, _):
            transport = WebSocketTransport()
            faults = Faults()

            def bad(message: JsonRpcNotification) -> None:
                raise asyncio.CancelledError

            transport.on("notification", bad)
            transport.on("error", faults)
            await transport.connect(url)
            await transport.send("rois.system.connect")
            await faults.first()

            assert await transport.send("vendor.ping") == {"return_code": "OK"}
            await transport.close()

    async def test_a_coroutine_listener_that_raises_is_a_fault(self) -> None:
        async with engine(pushes=(notification("vendor.one", {}),)) as (url, _):
            transport = WebSocketTransport()
            faults = Faults()

            async def bad(message: JsonRpcNotification) -> None:
                raise ValueError(message["method"])

            transport.on("notification", bad)
            transport.on("error", faults)
            await transport.connect(url)
            await transport.send("rois.system.connect")

            assert str(await faults.first()) == "vendor.one"
            await transport.close()

    async def test_an_error_listener_that_raises_is_logged(
        self, scripted_url: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        transport = await connected(f"{scripted_url}/malformed")

        def bad(error: Exception) -> None:
            raise ValueError("listener fault")

        transport.on("error", bad)
        with caplog.at_level(logging.ERROR, logger="openrois.sdk"):
            await transport.send(SEARCH, {"condition": "before"})

        assert "listener fault" in caplog.text
        await transport.close()

    async def test_a_coroutine_listener_can_await_a_request(self) -> None:
        # Run inline, this listener would wait for a reply that only the reader can deliver,
        # and the reader would be waiting for this listener.
        async with engine(pushes=(notification("vendor.one", {}),)) as (url, _):
            transport = WebSocketTransport()
            answered: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

            async def ask(message: JsonRpcNotification) -> None:
                answered.set_result(await transport.send("vendor.ping"))

            transport.on("notification", ask)
            await transport.connect(url)
            await transport.send("rois.system.connect")

            assert await asyncio.wait_for(answered, PROMPTLY) == {"return_code": "OK"}
            await transport.close()

    async def test_a_plain_listener_runs_before_the_next_message_is_read(self) -> None:
        pushes = tuple(notification(f"vendor.{n}", {}) for n in range(20))
        async with engine(pushes=pushes) as (url, _):
            transport = WebSocketTransport()
            order: list[str] = []
            transport.on("notification", lambda message: order.append(message["method"]))
            await transport.connect(url)
            await transport.send("rois.system.connect")
            await transport.send("vendor.ping")
            assert order == [f"vendor.{n}" for n in range(20)]
            await transport.close()

    async def test_a_notification_listener_gets_the_whole_message(self) -> None:
        bare = '{"jsonrpc": "2.0", "method": "vendor.two"}'
        pushes = (notification("vendor.one", {"n": 1}), bare)
        async with engine(pushes=pushes) as (url, _):
            transport = WebSocketTransport()
            seen: list[JsonRpcNotification] = []
            transport.on("notification", seen.append)
            await transport.connect(url)
            await transport.send("rois.system.connect")
            await transport.send("vendor.ping")
            assert seen == [
                {"jsonrpc": "2.0", "method": "vendor.one", "params": {"n": 1}},
                {"jsonrpc": "2.0", "method": "vendor.two"},
            ]
            await transport.close()

    async def test_a_notification_never_goes_out_under_its_own_name(self) -> None:
        async with engine(pushes=(notification("close", {}),)) as (url, _):
            transport = WebSocketTransport()
            closed: list[int] = []
            seen: list[str] = []
            transport.on("close", lambda code, _: closed.append(code))
            transport.on("notification", lambda message: seen.append(message["method"]))
            await transport.connect(url)
            await transport.send("rois.system.connect")
            await transport.send("vendor.ping")
            assert (closed, seen) == ([], ["close"])
            await transport.close()

    async def test_off_removes_a_listener_and_a_bound_method_matches_itself(
        self, scripted_url: str
    ) -> None:
        transport = await connected(f"{scripted_url}/malformed")
        faults = Faults()
        spare = Faults()
        transport.on("error", spare)
        transport.on("error", faults.__call__)
        transport.off("error", faults.__call__)

        await transport.send(SEARCH, {"condition": "before"})

        assert faults.seen == []
        assert len(spare.seen) == 2
        await transport.close()

    async def test_a_listener_can_remove_itself_without_skipping_the_next(
        self, scripted_url: str
    ) -> None:
        transport = await connected(f"{scripted_url}/malformed")
        once: list[Exception] = []
        always: list[Exception] = []

        def first_only(error: Exception) -> None:
            once.append(error)
            transport.off("error", first_only)

        transport.on("error", first_only)
        transport.on("error", always.append)

        await transport.send(SEARCH, {"condition": "before"})

        assert (len(once), len(always)) == (1, 2)
        await transport.close()


class TestClient:
    async def test_await_connect_gives_a_client(self, scripted_url: str) -> None:
        client = await RoISClient.connect(f"{scripted_url}/malformed")
        assert isinstance(client, RoISClient)
        await client.disconnect()

    async def test_async_with_connect_disconnects_when_the_block_ends(
        self, scripted_url: str
    ) -> None:
        async with RoISClient.connect(f"{scripted_url}/reverse") as client:
            closed = close_of(client)
        assert closed.result() == (1000, "client closed")

    async def test_async_with_a_connected_client_disconnects_too(self, scripted_url: str) -> None:
        async with await RoISClient.connect(f"{scripted_url}/reverse") as client:
            closed = close_of(client)
        assert closed.done()

    async def test_connect_passes_on_the_timeouts(self, scripted_url: str) -> None:
        url = f"{scripted_url}/reverse"
        async with RoISClient.connect(url, request_timeout=0.05) as client:
            with pytest.raises(RequestTimeoutError):
                await client.search("alone")

    async def test_a_refused_connect_raises_and_closes_the_connection(self) -> None:
        loop = asyncio.get_running_loop()
        ended: asyncio.Future[int | None] = loop.create_future()

        async def refuse(connection: ServerConnection) -> None:
            await connection.send(reply(json.loads(await connection.recv()), return_code="ERROR"))
            await connection.wait_closed()
            ended.set_result(connection.protocol.close_code)

        async with serving(refuse) as url:
            with pytest.raises(RoISError) as caught:
                await RoISClient.connect(url)
            assert await asyncio.wait_for(ended, PROMPTLY) == 1000
        assert caught.value.return_code is ReturnCode.ERROR
        assert caught.value.method == "rois.system.connect"

    @pytest.mark.parametrize("enter", ["await", "async with"])
    async def test_a_cancelled_connect_does_not_wait_for_a_silent_peer(self, enter: str) -> None:
        async def opened(url: str) -> None:
            if enter == "await":
                await RoISClient.connect(url)
            else:
                async with RoISClient.connect(url):
                    pytest.fail("connect gave a client")

        async with deaf() as (url, connections):
            started = asyncio.get_running_loop().time()
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.02):
                    await opened(url)

            # Waiting for this peer would take the 10 seconds of the closing handshake.
            assert asyncio.get_running_loop().time() - started < PROMPTLY
            connections[0].transport.resume_reading()
            await asyncio.wait_for(connections[0].wait_closed(), PROMPTLY)

    async def test_a_request_timeout_during_connect_does_not_wait_for_a_silent_peer(self) -> None:
        async with deaf() as (url, _):
            started = asyncio.get_running_loop().time()
            with pytest.raises(RequestTimeoutError):
                await RoISClient.connect(url, request_timeout=0.01)
            assert asyncio.get_running_loop().time() - started < PROMPTLY

    async def test_connect_fails_with_a_connection_error(self) -> None:
        with pytest.raises(RoISConnectionError):
            await RoISClient.connect(f"ws://127.0.0.1:{free_port()}")

    async def test_invalid_params_fail_before_anything_is_sent(self) -> None:
        async with engine() as (url, received):
            async with RoISClient.connect(url) as client:
                with pytest.raises(ValidationError):
                    await client.execute([])
                with pytest.raises(ValidationError):
                    await client.execute([{"component_ref": "a/b"}])
                with pytest.raises(ValidationError):
                    await client.set_parameter("a/b", [{"name": "only a name"}])
                await client.search()
        assert [request["method"] for request in received] == [
            "rois.system.connect",
            SEARCH,
            "rois.system.disconnect",
        ]

    async def test_a_return_code_other_than_ok_raises_rois_error(self) -> None:
        answers = {"rois.command.bind": lambda r: reply(r, return_code="OUT_OF_RESOURCES")}
        async with engine(answers) as (url, _):
            async with RoISClient.connect(url) as client:
                with pytest.raises(RoISError) as caught:
                    await client.bind("a/b")
        assert caught.value.return_code == "OUT_OF_RESOURCES"
        assert caught.value.method == "rois.command.bind"

    async def test_a_result_that_does_not_match_the_catalog_raises(self) -> None:
        async with engine({SEARCH: lambda r: reply(r, surprise=1)}) as (url, _):
            async with RoISClient.connect(url) as client:
                with pytest.raises(ValidationError):
                    await client.search()

    async def test_inputs_take_a_model_or_a_mapping(self) -> None:
        unit = {"component_ref": "a/b", "command_type": "start"}

        def assign(request: Message) -> str:
            return reply(
                request,
                command_unit_list=[
                    {"component_ref": "a/b", "command_type": "start", "command_id": "a"},
                    {
                        "branch_list": [
                            {
                                "command_list": [
                                    {
                                        "component_ref": "a/b",
                                        "command_type": "start",
                                        "command_id": "b",
                                    },
                                    {
                                        "component_ref": "a/b",
                                        "command_type": "stop",
                                        "command_id": "c",
                                    },
                                ]
                            },
                            {
                                "command_list": [
                                    {
                                        "component_ref": "a/b",
                                        "command_type": "start",
                                        "command_id": "d",
                                    }
                                ]
                            },
                        ]
                    },
                ],
            )

        async with engine({"rois.command.execute": assign}) as (url, received):
            async with RoISClient.connect(url) as client:
                ids = await client.execute(
                    [MappingProxyType(unit), {"branch_list": [{"command_list": [unit]}]}]
                )
        assert ids == ["a", "b", "c", "d"]
        sent = received[1]["params"]["command_unit_list"][0]
        assert sent["command_id"] == ""

    async def test_get_profile_passes_on_its_condition(self) -> None:
        async with engine() as (url, received):
            async with RoISClient.connect(url) as client:
                with pytest.raises(TransportError, match="without a profile"):
                    await client.get_profile("the condition")
        assert received[1]["params"] == {"condition": "the condition"}

    async def test_get_profile_ok_without_a_profile_is_refused(self) -> None:
        async with engine() as (url, _):
            async with RoISClient.connect(url) as client:
                with pytest.raises(TransportError, match="without a profile"):
                    await client.get_profile()

    async def test_a_listener_added_before_the_message_gets_model_params(self) -> None:
        async def later(connection: ServerConnection) -> None:
            async for raw in connection:
                request = json.loads(raw)
                if request["method"] == SEARCH:
                    params = {"command_id": "c-1", "status": "OK"}
                    await connection.send(notification(COMPLETED, params))
                await connection.send(reply(request))

        async with serving(later) as url:
            async with RoISClient.connect(url) as client:
                seen: list[CompletedParams] = []
                client.on(COMPLETED, seen.append)
                await client.search()
        assert [params.command_id for params in seen] == ["c-1"]
        assert isinstance(seen[0], CompletedParams)

    async def test_a_coroutine_listener_can_call_the_client(self) -> None:
        async def later(connection: ServerConnection) -> None:
            async for raw in connection:
                request = json.loads(raw)
                if request["params"].get("condition") == "first":
                    params = {"command_id": "c-1", "status": "OK"}
                    await connection.send(notification(COMPLETED, params))
                refs = [request["params"].get("condition", "")]
                answer = {"component_ref_list": refs} if request["method"] == SEARCH else {}
                await connection.send(reply(request, **answer))

        async with serving(later) as url:
            async with RoISClient.connect(url) as client:
                nested: asyncio.Future[list[str]] = asyncio.get_running_loop().create_future()

                async def ask(_: CompletedParams) -> None:
                    nested.set_result(await client.search("nested"))

                client.on(COMPLETED, ask)
                await client.search("first")
                assert await asyncio.wait_for(nested, PROMPTLY) == ["nested"]

    async def test_a_notification_with_bad_params_is_a_fault(self) -> None:
        async def later(connection: ServerConnection) -> None:
            async for raw in connection:
                request = json.loads(raw)
                if request["method"] == SEARCH:
                    await connection.send(notification(COMPLETED, {"unknown": 1}))
                await connection.send(reply(request))

        async with serving(later) as url:
            async with RoISClient.connect(url) as client:
                faults = Faults()
                seen: list[CompletedParams] = []
                client.on("error", faults)
                client.on(COMPLETED, seen.append)
                await client.search()
                assert "Invalid params" in str(await faults.first())
                assert seen == []

    async def test_a_notification_outside_the_catalog_stays_on_the_transport(self) -> None:
        async def later(connection: ServerConnection) -> None:
            async for raw in connection:
                request = json.loads(raw)
                if request["method"] == SEARCH:
                    await connection.send(notification("vendor.news", {"n": 1}))
                await connection.send(reply(request))

        async with serving(later) as url:
            async with RoISClient.connect(url) as client:
                faults = Faults()
                seen: list[object] = []
                client.on("error", faults)
                client.transport.on("notification", lambda n: seen.append(n["params"]))
                await client.search()
                assert seen == [{"n": 1}]
                assert faults.seen == []

    async def test_a_transport_fault_reaches_the_client_error_listener(
        self, scripted_url: str
    ) -> None:
        async with RoISClient.connect(f"{scripted_url}/malformed") as client:
            faults = Faults()
            client.on("error", faults)
            assert await client.search("before") == ["before"]
            assert len(faults.seen) == 2

    async def test_a_lost_connection_fails_calls_locally_afterwards(
        self, scripted_url: str
    ) -> None:
        client = await RoISClient.connect(f"{scripted_url}/drop")
        closed = close_of(client)
        with pytest.raises(RoISConnectionError):
            await client.search("one")
        assert (await closed)[0] == 1006
        with pytest.raises(TransportError, match="not connected"):
            await client.search("two")
        await client.disconnect()

    async def test_disconnect_is_safe_twice_and_a_call_after_it_fails_locally(self) -> None:
        async with engine() as (url, received):
            client = await RoISClient.connect(url)
            closes: list[int] = []
            client.on("close", lambda code, _: closes.append(code))

            await client.disconnect()
            await client.disconnect()

            assert closes == [1000]
            with pytest.raises(TransportError, match="not connected"):
                await client.search()
        assert [r["method"] for r in received].count("rois.system.disconnect") == 1

    async def test_overlapping_disconnects_send_one_request(self) -> None:
        async with engine() as (url, received):
            client = await RoISClient.connect(url)
            await asyncio.gather(
                client.disconnect(),
                client.disconnect(),
                client.__aexit__(None, None, None),
            )
        assert [r["method"] for r in received].count("rois.system.disconnect") == 1

    async def test_one_cancelled_disconnect_leaves_another_caller_its_outcome(self) -> None:
        answering = asyncio.Event()

        async def slow(connection: ServerConnection) -> None:
            async for raw in connection:
                request = json.loads(raw)
                if request["method"] == "rois.system.disconnect":
                    await answering.wait()
                await connection.send(reply(request))

        async with serving(slow) as url:
            client = await RoISClient.connect(url)
            first = asyncio.create_task(client.disconnect())
            second = asyncio.create_task(client.disconnect())
            await asyncio.sleep(0.01)

            first.cancel()

            with pytest.raises(asyncio.CancelledError):
                await first
            answering.set()
            await asyncio.wait_for(second, PROMPTLY)
            assert client.transport.state is TransportState.DISCONNECTED

    async def test_disconnect_after_a_cancelled_reader_ends_at_once(self) -> None:
        async with engine() as (url, _):
            client = await RoISClient.connect(url)
            closed = close_of(client)
            assert client.transport._reader is not None

            client.transport._reader.cancel()
            await asyncio.wait_for(closed, PROMPTLY)

            await asyncio.wait_for(client.disconnect(), PROMPTLY)
            with pytest.raises(TransportError, match="not connected"):
                await client.search()

    async def test_the_connection_closes_when_the_engine_refuses_disconnect(self) -> None:
        answers = {"rois.system.disconnect": lambda r: reply(r, return_code="ERROR")}
        async with engine(answers) as (url, _):
            client = await RoISClient.connect(url)
            with pytest.raises(RoISError):
                await client.disconnect()
            assert client.transport.state is TransportState.DISCONNECTED
