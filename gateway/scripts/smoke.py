"""End-to-end check of a gateway with the mock adapter behind it.

Connects to the gateway as a client and checks, in order:

1. The mock adapter's components appear in rois.system.get_profile.
2. A query to one of them returns OK.
3. An event the adapter fires reaches this client.

Retries the connection and the profile until --timeout, so it can run right
after ``docker compose up``. Prints one line per check and exits with 0 when
every check passes, 1 otherwise. Needs only the websockets package.

Usage:
    python gateway/scripts/smoke.py [--url ws://127.0.0.1:8765] [--timeout 60]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import InvalidHandshake


class SmokeError(Exception):
    """A check failed."""


class Client:
    """A minimal JSON-RPC client that keeps notifications for later."""

    def __init__(self, connection: ClientConnection) -> None:
        self.connection = connection
        self.notifications: list[dict[str, Any]] = []
        self._next_id = 0

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        await self.connection.send(json.dumps(message))
        while True:
            reply: dict[str, Any] = json.loads(await self.connection.recv())
            if reply.get("id") != request_id:
                self.notifications.append(reply)
                continue
            if "error" in reply:
                raise SmokeError(f"{method} failed: {reply['error']}")
            result: dict[str, Any] = reply["result"]
            return result

    async def notification(self, method: str, timeout: float) -> dict[str, Any]:
        for index, message in enumerate(self.notifications):
            if message.get("method") == method:
                params: dict[str, Any] = self.notifications.pop(index).get("params", {})
                return params
        async with asyncio.timeout(timeout):
            while True:
                message = json.loads(await self.connection.recv())
                if message.get("method") == method:
                    found: dict[str, Any] = message.get("params", {})
                    return found


async def connect_with_retry(url: str, deadline: float) -> ClientConnection:
    loop = asyncio.get_running_loop()
    while True:
        try:
            return await connect(url)
        except (OSError, TimeoutError, InvalidHandshake) as exc:
            if loop.time() > deadline:
                raise SmokeError(f"Cannot connect to {url}: {exc}") from exc
            await asyncio.sleep(1.0)


async def run(url: str, engine_id: str, timeout: float) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    detection = f"{engine_id}/ObjectDetection"

    async with await connect_with_retry(url, deadline) as connection:
        client = Client(connection)
        print(f"ok   connected to {url}")

        while True:
            profile = (await client.call("rois.system.get_profile"))["profile"]
            if detection in profile.get("component_ids", []):
                break
            if loop.time() > deadline:
                raise SmokeError(f"{detection} did not appear in the profile within {timeout}s")
            await asyncio.sleep(1.0)
        print(f"ok   {engine_id} registered: {', '.join(profile['component_ids'])}")

        query = await client.call(
            "rois.query.query",
            {"component_ref": f"{engine_id}/SystemInformation", "query_type": "robot_position"},
        )
        if query.get("return_code") != "OK":
            raise SmokeError(f"robot_position returned {query.get('return_code')}")
        print("ok   robot_position query answered")

        subscribed = await client.call(
            "rois.event.subscribe", {"component_ref": detection, "event_type": "object_detected"}
        )
        if subscribed.get("return_code") != "OK":
            raise SmokeError(f"subscribe returned {subscribed.get('return_code')}")
        # The mock adapter fires object_detected three seconds after a subscription.
        try:
            event = await client.notification("rois.event.notify", timeout=10.0)
        except TimeoutError as exc:
            raise SmokeError("object_detected did not arrive within 10s") from exc
        if event.get("subscribe_id") != subscribed["subscribe_id"]:
            raise SmokeError(f"event for an unknown subscription: {event}")
        print("ok   object_detected event relayed")

        await client.call("rois.event.unsubscribe", {"subscribe_id": subscribed["subscribe_id"]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="ws://127.0.0.1:8765", help="gateway URL")
    parser.add_argument("--engine-id", default="mock_robot", help="engine id of the mock adapter")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for startup")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.url, args.engine_id, args.timeout))
    except SmokeError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
