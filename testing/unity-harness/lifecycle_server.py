"""A WebSocket server that records what a client does, for the Play Mode run of the harness.

The Editor run has to show that a client ended from the side of the peer, because a client
that only believes it ended would pass any check made inside the Editor. A client picks a
behavior with the first part of the path of its URL, and names itself with the second:

    /record/<tag>    Answers every request with OK.
    /deaf/<tag>      Answers rois.system.connect, then nothing, as an engine that hangs.
    /silent/<tag>    Answers nothing, so an attempt to connect stays in flight.

Each thing that happens is one line of the record file, flushed at once, so the Editor can
read it while the server runs:

    <tag> open
    <tag> method <method>
    <tag> close <code>

The server prints the port it binds on a line of its own, and runs until it is stopped. It
needs only the websockets package.

Usage:
    python testing/unity-harness/lifecycle_server.py --record PATH [--host 127.0.0.1] [--port 0]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import TextIO

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

CONNECT = "rois.system.connect"


def write(record: TextIO, line: str) -> None:
    """Add a line where the Editor can read it at once."""
    record.write(line + "\n")
    record.flush()


def answers(behavior: str, method: str) -> bool:
    """Whether a behavior replies to a method."""
    if behavior == "record":
        return True
    return behavior == "deaf" and method == CONNECT


async def handle(connection: ServerConnection, record: TextIO) -> None:
    """Record one client until it leaves, however it leaves."""
    assert connection.request is not None
    _, behavior, tag = connection.request.path.split("/")
    write(record, f"{tag} open")
    try:
        async for raw in connection:
            request = json.loads(raw)
            write(record, f"{tag} method {request['method']}")
            if answers(behavior, request["method"]):
                result = {"return_code": "OK"}
                await connection.send(
                    json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result})
                )
    except ConnectionClosed:
        # A dropped client is a result here. The close line below records it.
        pass
    code = connection.close_code if connection.close_code is not None else 1006
    write(record, f"{tag} close {code}")


async def run(host: str, port: int, path: Path) -> None:
    """Serve until the process is stopped."""
    with path.open("a", encoding="utf-8") as record:

        async def handler(connection: ServerConnection) -> None:
            await handle(connection, record)

        async with serve(handler, host, port) as server:
            print(server.sockets[0].getsockname()[1], flush=True)
            await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 lets the system pick a free port")
    parser.add_argument("--record", type=Path, required=True, help="the file to append to")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.host, args.port, args.record))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
