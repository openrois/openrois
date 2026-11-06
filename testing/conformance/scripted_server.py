"""A WebSocket server with no engine, for scenarios C18 to C21 of the conformance list.

These scenarios test how a client handles a server, so the server has to misbehave on cue.
A client picks a script with the path of its URL, which needs no control channel, so one
process serves every language and a browser:

    /reverse      Holds requests until three have arrived, then answers the last one first.
    /malformed    Sends each message of ``MALFORMED`` before it answers the first request.
    /drop         Drops the connection without a close frame after the first request.
    /close-1001   Answers the first request, then closes with 1001 and ``CLOSE_REASON``.

Any other path fails the handshake with 404, so a typo in a test does not end in a timeout.

Every script acts on a request, never on connect, so a client has time to add its listeners
first. ``rois.system.connect`` and ``rois.system.disconnect`` are answered with OK on every
path, so a client goes through its usual session. ``rois.command.search`` answers with its
condition as the only component ref, which lets a caller recognize its own reply. Every
other method answers with OK and nothing else.

The server prints the port it binds on a line of its own, for a test runner to read, and
runs until it is stopped. It needs only the websockets package.

Usage:
    python testing/conformance/scripted_server.py [--host 127.0.0.1] [--port 0]
"""

from __future__ import annotations

import argparse
import asyncio
import http
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

type Message = dict[str, Any]
type Script = Callable[[ServerConnection], Awaitable[None]]

CONNECT = "rois.system.connect"
DISCONNECT = "rois.system.disconnect"
SEARCH = "rois.command.search"

#: How many requests ``/reverse`` holds before it answers them.
REVERSE_COUNT = 3

#: Text that is not JSON, then JSON that is neither a reply nor a notification.
MALFORMED = ("{not json", '{"jsonrpc": "2.0"}')

#: The seconds ``/drop`` waits, so that every request of a burst is in flight when it drops.
DROP_DELAY = 0.05

CLOSE_REASON = "scripted close"


def reply(request: Message) -> str:
    """The reply to a request, which every script sends unchanged."""
    result: Message = {"return_code": "OK"}
    if request["method"] == SEARCH:
        result["component_ref_list"] = [request["params"]["condition"]]
    return json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result})


async def requests(connection: ServerConnection) -> AsyncIterator[Message]:
    """Yield what a client sends, past the two calls that open and end its session."""
    async for raw in connection:
        request: Message = json.loads(raw)
        if request["method"] in (CONNECT, DISCONNECT):
            await connection.send(reply(request))
        else:
            yield request


async def reverse(connection: ServerConnection) -> None:
    """Answer each group of requests last first."""
    held: list[Message] = []
    async for request in requests(connection):
        held.append(request)
        if len(held) == REVERSE_COUNT:
            for waiting in reversed(held):
                await connection.send(reply(waiting))
            held.clear()


async def malformed(connection: ServerConnection) -> None:
    """Send the malformed messages once, ahead of a reply that proves the client still works."""
    unsent = list(MALFORMED)
    async for request in requests(connection):
        for message in unsent:
            await connection.send(message)
        unsent.clear()
        await connection.send(reply(request))


async def drop(connection: ServerConnection) -> None:
    """Leave without a close frame, as a crash or a lost network does."""
    async for _ in requests(connection):
        await asyncio.sleep(DROP_DELAY)
        connection.transport.abort()
        return


async def close_1001(connection: ServerConnection) -> None:
    """Close as a server that stops does."""
    async for request in requests(connection):
        await connection.send(reply(request))
        await connection.close(1001, CLOSE_REASON)
        return


SCRIPTS: dict[str, Script] = {
    "/reverse": reverse,
    "/malformed": malformed,
    "/drop": drop,
    "/close-1001": close_1001,
}


def reject_unknown_path(connection: ServerConnection, request: Request) -> Response | None:
    """Fail the handshake of a path that names no script."""
    if request.path in SCRIPTS:
        return None
    known = ", ".join(SCRIPTS)
    return connection.respond(http.HTTPStatus.NOT_FOUND, f"{request.path} is not {known}\n")


async def handle(connection: ServerConnection) -> None:
    """Run the script of the path this client connected to."""
    assert connection.request is not None
    try:
        await SCRIPTS[connection.request.path](connection)
    except ConnectionClosed:
        # A client may leave in the middle of a script, and the next one is unaffected.
        pass


async def run(host: str, port: int) -> None:
    """Serve until the process is stopped."""
    async with serve(handle, host, port, process_request=reject_unknown_path) as server:
        print(server.sockets[0].getsockname()[1], flush=True)
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 lets the system pick a free port")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
