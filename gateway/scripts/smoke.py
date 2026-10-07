"""End-to-end check of a gateway with the mock adapter behind it.

Connects to the gateway as a client and checks, in order:

1. The components of the mock adapter appear in rois.command.search.
2. get_profile lists the adapter as a sub profile, with a profile for each component.
3. robot_position and component_status answer OK.
4. A person_detected event reaches this client, and get_event_detail reads it.
5. A navigation runs: bind, set_parameter, execute start, its rois.command.completed,
   the reached_target event at the target that was set, get_command_result, release.
6. A method outside the catalog is answered with METHOD_NOT_FOUND.

Retries the connection and the search until --timeout, so it can run right after
``docker compose up``. Prints one line per check and exits with 0 when every check
passes, 1 otherwise. Needs only the websockets package.

Usage:
    python gateway/scripts/smoke.py [--url ws://127.0.0.1:8765] [--engine-id mock]
        [--timeout 60] [--event-timeout 15]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Callable
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake


class SmokeError(Exception):
    """A check failed."""


def ref_is(ref: str) -> str:
    """A condition that selects one component, in the CQL2-Text subset of OpenRoIS."""
    return "component_ref = '" + ref.replace("'", "''") + "'"


class Client:
    """A minimal JSON-RPC client: replies by id, notifications kept in arrival order."""

    def __init__(self, connection: ClientConnection) -> None:
        self.connection = connection
        self.notifications: list[dict[str, Any]] = []
        self._replies: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._arrived = asyncio.Event()
        self._next_id = 0
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        try:
            async for raw in self.connection:
                message: dict[str, Any] = json.loads(raw)
                future = self._replies.pop(message["id"], None) if "id" in message else None
                if future is not None:
                    future.set_result(message)
                elif "method" in message:
                    self.notifications.append(message)
                    self._arrived.set()
        except ConnectionClosed:
            pass
        finally:
            for future in self._replies.values():
                future.set_exception(SmokeError("The gateway closed the connection."))

    async def reply(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send one request and return the whole reply."""
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._replies[self._next_id] = future
        message = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}}
        await self.connection.send(json.dumps(message))
        async with asyncio.timeout(10.0):
            return await future

    async def call(
        self, method: str, params: dict[str, Any] | None = None, *, expect: str = "OK"
    ) -> dict[str, Any]:
        """Send one request and return its result, which must carry ``expect``."""
        reply = await self.reply(method, params)
        if "error" in reply:
            raise SmokeError(f"{method} failed: {reply['error']}")
        result: dict[str, Any] = reply["result"]
        if result.get("return_code") != expect:
            raise SmokeError(f"{method} returned {result.get('return_code')}, not {expect}")
        return result

    async def notification(
        self, method: str, match: Callable[[dict[str, Any]], bool], timeout: float
    ) -> dict[str, Any]:
        """Wait for a notification of one method whose params match, and return them."""
        async with asyncio.timeout(timeout):
            while True:
                for message in self.notifications:
                    params: dict[str, Any] = message.get("params", {})
                    if message.get("method") == method and match(params):
                        self.notifications.remove(message)
                        return params
                self._arrived.clear()
                await self._arrived.wait()

    async def close(self) -> None:
        await self.connection.close()
        await self._reader


async def connect_with_retry(url: str, deadline: float) -> ClientConnection:
    loop = asyncio.get_running_loop()
    while True:
        try:
            return await connect(url)
        except (OSError, TimeoutError, InvalidHandshake) as exc:
            if loop.time() > deadline:
                raise SmokeError(f"Cannot connect to {url}: {exc}") from exc
            await asyncio.sleep(1.0)


async def run(url: str, engine_id: str, timeout: float, event_timeout: float) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    detection = f"{engine_id}/person_detection"
    navigation = f"{engine_id}/navigation"
    information = f"{engine_id}/system_information"

    client = Client(await connect_with_retry(url, deadline))
    try:
        print(f"ok   connected to {url}")

        # 1. The adapter registers once the gateway has read its profile.
        wanted = {detection, navigation, information}
        while True:
            found = (await client.call("rois.command.search", {"condition": ""}))[
                "component_ref_list"
            ]
            if wanted <= set(found):
                break
            if loop.time() > deadline:
                raise SmokeError(f"{', '.join(sorted(wanted))} did not appear within {timeout}s")
            await asyncio.sleep(1.0)
        print(f"ok   {engine_id} registered: {', '.join(found)}")

        # 2. The profile names the adapter and serves a profile for each component.
        profile = await client.call("rois.system.get_profile", {"condition": ""})
        engines = [p["identifier"]["code"] for p in profile["profile"]["sub_profiles"]]
        if engine_id not in engines:
            raise SmokeError(f"{engine_id} is not a sub profile of the gateway: {engines}")
        missing = wanted - set(profile["component_profiles"])
        if missing:
            raise SmokeError(f"No component profile for {', '.join(sorted(missing))}")
        print(f"ok   get_profile lists {engine_id} with its component profiles")

        # 3. Queries.
        await client.call(
            "rois.query.query", {"query_type": "robot_position", "condition": ref_is(information)}
        )
        status = await client.call(
            "rois.query.query", {"query_type": "component_status", "condition": ref_is(navigation)}
        )
        print(f"ok   robot_position answered, navigation is {status['results'][0]['value']}")

        # 4. An event the adapter emits on its own.
        detected = await client.call(
            "rois.event.subscribe",
            {"event_type": "person_detected", "condition": ref_is(detection)},
        )
        try:
            event = await client.notification(
                "rois.event.notify_event",
                lambda p: p.get("subscribe_id") == detected["subscribe_id"],
                event_timeout,
            )
        except TimeoutError as exc:
            raise SmokeError(f"person_detected did not arrive within {event_timeout}s") from exc
        detail = await client.call(
            "rois.event.get_event_detail", {"event_id": event["event_id"], "condition": ""}
        )
        if detail["results"] != event["results"]:
            raise SmokeError(f"get_event_detail differs from the event: {detail['results']}")
        await client.call("rois.event.unsubscribe", {"subscribe_id": detected["subscribe_id"]})
        print(f"ok   person_detected relayed as {event['event_id']} and read back")

        # 5. A navigation, from the binding to the event.
        await client.call("rois.command.bind", {"component_ref": navigation})
        target = "kitchen"
        configured = await client.call(
            "rois.command.set_parameter",
            {
                "component_ref": navigation,
                "parameters": [
                    {
                        "name": "target_positions",
                        "data_type_ref": "string[]",
                        "value": json.dumps([target]),
                    }
                ],
            },
        )
        await completed(client, configured["command_id"], event_timeout)
        reached = await client.call(
            "rois.event.subscribe",
            {"event_type": "reached_target", "condition": ref_is(navigation)},
        )
        command_id = f"smoke-{uuid.uuid4().hex[:12]}"
        start = {
            "component_ref": navigation,
            "command_type": "start",
            "command_id": command_id,
            "arguments": [],
        }
        await client.call("rois.command.execute", {"command_unit_list": [start]})
        await completed(client, command_id, event_timeout)
        try:
            arrival = await client.notification(
                "rois.event.notify_event",
                lambda p: p.get("subscribe_id") == reached["subscribe_id"],
                event_timeout,
            )
        except TimeoutError as exc:
            raise SmokeError(f"reached_target did not arrive within {event_timeout}s") from exc
        values = {r["name"]: r["value"] for r in arrival["results"]}
        if values.get("target") != target:
            raise SmokeError(f"reached_target names {values.get('target')!r}, not {target!r}")
        await client.call(
            "rois.command.get_command_result", {"command_id": command_id, "condition": ""}
        )
        await client.call("rois.event.unsubscribe", {"subscribe_id": reached["subscribe_id"]})
        await client.call("rois.command.release", {"component_ref": navigation})
        print(f"ok   navigation to {target} completed with reached_target")

        # 6. The protocol.
        reply = await client.reply("rois.stream.connect_stream", {})
        if reply.get("error", {}).get("code") != -32601:
            raise SmokeError(f"rois.stream.connect_stream was not METHOD_NOT_FOUND: {reply}")
        print("ok   a method outside the catalog is METHOD_NOT_FOUND")
    finally:
        await client.close()


async def completed(client: Client, command_id: str, timeout: float) -> None:
    """Wait for a command's rois.command.completed, which must report OK."""
    try:
        params = await client.notification(
            "rois.command.completed", lambda p: p.get("command_id") == command_id, timeout
        )
    except TimeoutError as exc:
        raise SmokeError(f"{command_id} did not complete within {timeout}s") from exc
    if params.get("status") != "OK":
        raise SmokeError(f"{command_id} completed with {params.get('status')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="ws://127.0.0.1:8765", help="gateway URL")
    parser.add_argument("--engine-id", default="mock", help="engine id of the mock adapter")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for startup")
    parser.add_argument(
        "--event-timeout", type=float, default=15.0, help="seconds to wait for each event"
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(args.url, args.engine_id, args.timeout, args.event_timeout))
    except SmokeError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
