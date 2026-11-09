"""Scripted server checks on raw WebSocket messages, with no SDK and no engine.

This proves ``scripted_server.py`` itself, by reading what each script puts on the wire, so a
failure in an SDK's C18 to C21 tests points at the SDK. It starts the server the way a test
runner does and reads the port from its output. It prints one line per script and exits with
0 when every one passes, 1 otherwise. It needs only the websockets package.

Usage:
    python testing/conformance/scripted_check.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from scripted_server import CLOSE_REASON, CONNECT, DISCONNECT, MALFORMED, REVERSE_COUNT, SEARCH
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

type Message = dict[str, Any]
type Check = Callable[[int], Awaitable[None]]

SERVER = Path(__file__).with_name("scripted_server.py")

#: The seconds one check may take, far above what the scripts need.
TIMEOUT = 5.0


class CheckFailed(Exception):
    """A script put something on the wire that it should not have."""


def check(condition: object, message: str) -> None:
    """Fail the check with ``message`` unless ``condition`` holds."""
    if not condition:
        raise CheckFailed(message)


async def call(connection: ClientConnection, request_id: int, method: str, **params: Any) -> None:
    """Send a request without waiting for its reply, which is what a held request needs."""
    message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    await connection.send(json.dumps(message))


async def read(connection: ClientConnection) -> Message:
    """Read the next message as a JSON object."""
    message: Message = json.loads(await connection.recv())
    return message


def is_found(message: Message, request_id: int, condition: str) -> bool:
    """Whether a message is the reply to a search for ``condition``."""
    return message.get("id") == request_id and message.get("result") == {
        "return_code": "OK",
        "component_ref_list": [condition],
    }


@asynccontextmanager
async def session(port: int, path: str) -> AsyncIterator[ClientConnection]:
    """Open a connection on a script and run connect, as every client does."""
    async with connect(f"ws://127.0.0.1:{port}{path}") as connection:
        await call(connection, 1, CONNECT)
        answer = await read(connection)
        check(answer.get("result") == {"return_code": "OK"}, f"connect answered {answer}")
        yield connection


async def reverse(port: int) -> None:
    async with session(port, "/reverse") as connection:
        for _ in range(2):
            sent = [(number + 2, f"ref{number}") for number in range(REVERSE_COUNT)]
            for request_id, condition in sent:
                await call(connection, request_id, SEARCH, condition=condition)
            for request_id, condition in reversed(sent):
                answer = await read(connection)
                check(is_found(answer, request_id, condition), f"got {answer} out of order")
        await call(connection, 9, DISCONNECT)
        answer = await read(connection)
        check(answer == {"jsonrpc": "2.0", "id": 9, "result": {"return_code": "OK"}}, str(answer))


async def malformed(port: int) -> None:
    async with session(port, "/malformed") as connection:
        await call(connection, 2, SEARCH, condition="first")
        for expected in MALFORMED:
            raw = await connection.recv()
            check(raw == expected, f"expected {expected!r}, got {raw!r}")
        answer = await read(connection)
        check(is_found(answer, 2, "first"), f"after the malformed messages, got {answer}")
        await call(connection, 3, SEARCH, condition="second")
        answer = await read(connection)
        check(is_found(answer, 3, "second"), f"the next request got {answer}")


async def drop(port: int) -> None:
    async with session(port, "/drop") as connection:
        await call(connection, 2, SEARCH, condition="one")
        await call(connection, 3, SEARCH, condition="two")
        try:
            raw = await connection.recv()
        except ConnectionClosed as exc:
            check(exc.rcvd is None, f"a close frame arrived: {exc.rcvd}")
        else:
            raise CheckFailed(f"the requests got {raw!r} instead of a drop")


async def close_1001(port: int) -> None:
    async with session(port, "/close-1001") as connection:
        await call(connection, 2, SEARCH, condition="last")
        answer = await read(connection)
        check(is_found(answer, 2, "last"), f"the request got {answer}")
        try:
            raw = await connection.recv()
        except ConnectionClosed as exc:
            check(exc.rcvd is not None, "the connection dropped with no close frame")
            assert exc.rcvd is not None
            check(exc.rcvd.code == 1001, f"closed with {exc.rcvd.code}")
            check(exc.rcvd.reason == CLOSE_REASON, f"closed with reason {exc.rcvd.reason!r}")
        else:
            raise CheckFailed(f"got {raw!r} instead of a close")


async def unknown_path(port: int) -> None:
    try:
        async with connect(f"ws://127.0.0.1:{port}/nothing"):
            raise CheckFailed("the handshake succeeded")
    except InvalidStatus as exc:
        check(exc.response.status_code == 404, f"answered {exc.response.status_code}")


CHECKS: tuple[tuple[str, str, Check], ...] = (
    ("C18", "/reverse answers each group of requests last first", reverse),
    ("C19", "/malformed sends its messages, then keeps answering", malformed),
    ("C20", "/drop leaves with no close frame", drop),
    ("C21", "/close-1001 answers, then closes with its code and reason", close_1001),
    ("404", "an unknown path fails the handshake with 404", unknown_path),
)


async def run_checks() -> int:
    """Start the server, run every check on one process, and return the exit code."""
    server = await asyncio.create_subprocess_exec(
        sys.executable, str(SERVER), stdout=asyncio.subprocess.PIPE
    )
    failed = 0
    try:
        assert server.stdout is not None
        port = int(await asyncio.wait_for(server.stdout.readline(), TIMEOUT))
        for check_id, title, function in CHECKS:
            try:
                async with asyncio.timeout(TIMEOUT):
                    await function(port)
                print(f"ok   {check_id} {title}")
            except (CheckFailed, OSError, TimeoutError, ConnectionClosed, ValueError) as exc:
                failed += 1
                print(f"FAIL {check_id} {title}: {exc or type(exc).__name__}")
    finally:
        server.terminate()
        await server.wait()
    print(f"{len(CHECKS) - failed} of {len(CHECKS)} checks passed")
    return 1 if failed else 0


def main() -> None:
    sys.exit(asyncio.run(run_checks()))


if __name__ == "__main__":
    main()
