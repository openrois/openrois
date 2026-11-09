"""The conformance list on raw JSON-RPC, against a gateway with the mock adapter behind it.

This proves the engine and the gateway with no SDK in the way. Each scenario opens its
own connections, so one failure does not hide the next, and prints one line. The ids are
those of ``testing/conformance/README.md``. Scenarios that start with ``W`` cover what a
client SDK cannot reach. The list retries until the components of the mock adapter appear,
so it can run right after ``docker compose up``, and exits with 0 when every scenario
passes, 1 otherwise. It needs only the websockets package.

``--watch-close`` runs nothing. It holds one connection open and exits with 0 when the
gateway closes it with code 1001, to check a graceful stop.

Usage:
    python testing/conformance/wire_check.py [--url ws://127.0.0.1:8765] [--engine-id mock]
        [--timeout 60] [--event-timeout 20]
    python testing/conformance/wire_check.py --watch-close [--url ws://127.0.0.1:8765]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

type Message = dict[str, Any]
type Scenario = Callable[[Stack], Awaitable[None]]

COMPLETED = "rois.command.completed"
NOTIFY_EVENT = "rois.event.notify_event"
NOTIFY_ERROR = "rois.system.notify_error"
PROFILE_CHANGED = "rois.system.profile_changed"
NAVIGATION_URN = "urn:x-rois:def:component:OMG::Navigation"

#: Above the 1 MiB that the gateway accepts in one message.
TOO_LARGE = 2 * 1024 * 1024

#: How many commands the scenario on the order of replies and notifications runs.
ORDER_TRIES = 100


class CheckFailed(Exception):
    """A scenario saw something the contract does not allow."""


def check(condition: object, message: str) -> None:
    """Fail the scenario with ``message`` unless ``condition`` holds."""
    if not condition:
        raise CheckFailed(message)


def ref_is(ref: str) -> str:
    """A condition that selects one component, in the CQL2-Text subset of OpenRoIS."""
    return "component_ref = '" + ref.replace("'", "''") + "'"


def command_ids(result: Message) -> list[str]:
    """The ids of an execute result in order, branch by branch."""
    ids: list[str] = []
    for item in result["command_unit_list"]:
        if "branch_list" in item:
            for branch in item["branch_list"]:
                ids += [unit["command_id"] for unit in branch["command_list"]]
        else:
            ids.append(item["command_id"])
    return ids


class Client:
    """A JSON-RPC client that matches replies by id and records every message in order."""

    def __init__(self, connection: ClientConnection, timeout: float) -> None:
        self.connection = connection
        self.timeout = timeout
        self.messages: list[Message] = []
        self.close_code: int | None = None
        self._replies: dict[int, asyncio.Future[Message]] = {}
        self._arrived = asyncio.Event()
        self._next_id = 0
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        try:
            async for raw in self.connection:
                message: Message = json.loads(raw)
                self.messages.append(message)
                reply = self._replies.pop(message["id"], None) if "id" in message else None
                if reply is not None:
                    reply.set_result(message)
                self._arrived.set()
        except ConnectionClosed:
            pass
        self.close_code = self.connection.close_code
        self._arrived.set()

    async def request(self, method: str, params: Message | None = None) -> Message:
        """Send a request and return the whole reply."""
        self._next_id += 1
        reply: asyncio.Future[Message] = asyncio.get_running_loop().create_future()
        self._replies[self._next_id] = reply
        await self.connection.send(
            json.dumps(
                {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}}
            )
        )
        return await asyncio.wait_for(reply, self.timeout)

    async def call(self, method: str, **params: Any) -> Message:
        """Send a request and return its result."""
        reply = await self.request(method, params)
        check("result" in reply, f"{method} answered {reply}")
        result: Message = reply["result"]
        return result

    async def ok(self, method: str, **params: Any) -> Message:
        """Send a request whose return code must be OK."""
        result = await self.call(method, **params)
        check(result["return_code"] == "OK", f"{method} answered {result}")
        return result

    async def execute(self, *items: Message) -> list[str]:
        """Run an execute that must be accepted, and return the assigned ids."""
        result = await self.ok("rois.command.execute", command_unit_list=list(items))
        return command_ids(result)

    def sent(self, method: str) -> list[Message]:
        """The params of every notification of one method received so far."""
        return [m["params"] for m in self.messages if m.get("method") == method]

    async def until(self, ready: Callable[[], Any], timeout: float, what: str) -> Any:
        """Wait until ``ready`` returns something true, and return it."""
        deadline = time.monotonic() + timeout
        while True:
            value = ready()
            if value:
                return value
            self._arrived.clear()
            left = deadline - time.monotonic()
            check(left > 0, f"no {what} within {timeout} seconds")
            try:
                await asyncio.wait_for(self._arrived.wait(), left)
            except TimeoutError:
                pass

    async def notification(
        self, method: str, match: Callable[[Message], bool], timeout: float
    ) -> Message:
        """Wait for a notification of one method whose params match."""
        found: Message = await self.until(
            lambda: next((p for p in self.sent(method) if match(p)), None), timeout, method
        )
        return found

    async def completed(self, command_id: str, timeout: float) -> str:
        """Wait for the completed notification of a command and return its status."""
        params = await self.notification(
            COMPLETED, lambda p: p["command_id"] == command_id, timeout
        )
        status: str = params["status"]
        return status

    async def close(self) -> None:
        await self.connection.close()
        await self._reader


@dataclass(frozen=True)
class Stack:
    """The gateway under test and the time it gets."""

    url: str
    engine_id: str
    event_timeout: float
    request_timeout: float = 15.0

    @property
    def navigation(self) -> str:
        return f"{self.engine_id}/navigation"

    @property
    def detection(self) -> str:
        return f"{self.engine_id}/person_detection"

    @property
    def information(self) -> str:
        return f"{self.engine_id}/system_information"

    @property
    def fault(self) -> str:
        return f"{self.engine_id}/fault"

    @asynccontextmanager
    async def session(self, *, handshake: bool = True) -> AsyncIterator[Client]:
        """A client on its own connection, closed however the scenario ends."""
        client = Client(await connect(self.url), self.request_timeout)
        try:
            if handshake:
                await client.ok("rois.system.connect")
            yield client
        finally:
            await client.close()

    async def set_targets(self, client: Client, value: str) -> str:
        """Set target_positions on a bound navigation, and return the command id."""
        result = await client.ok(
            "rois.command.set_parameter",
            component_ref=self.navigation,
            parameters=[{"name": "target_positions", "data_type_ref": "string[]", "value": value}],
        )
        command_id: str = result["command_id"]
        return command_id


SCENARIOS: list[tuple[str, str, Scenario]] = []


def scenario(scenario_id: str, title: str) -> Callable[[Scenario], Scenario]:
    """Add a scenario to the list, in the order of this file."""

    def add(function: Scenario) -> Scenario:
        SCENARIOS.append((scenario_id, title, function))
        return function

    return add


@scenario("W01", "requests before connect and after disconnect answer ERROR")
async def requests_outside_a_session(stack: Stack) -> None:
    async with stack.session(handshake=False) as client:
        before = await client.call("rois.command.search", condition="")
        check(before["return_code"] == "ERROR", f"before connect: {before}")
        await client.ok("rois.system.connect")
        await client.ok("rois.system.disconnect")
        after = await client.call("rois.command.search", condition="")
        check(after["return_code"] == "ERROR", f"after disconnect: {after}")


@scenario("C02", "get_profile lists the sub profile and each component profile")
async def profile(stack: Stack) -> None:
    async with stack.session() as client:
        result = await client.ok("rois.system.get_profile", condition="")
        engines = [p["identifier"]["code"] for p in result["profile"]["sub_profiles"]]
        check(stack.engine_id in engines, f"sub profiles: {engines}")
        for ref in (stack.navigation, stack.detection, stack.information, stack.fault):
            check(ref in result["component_profiles"], f"no profile for {ref}")


@scenario("C03", "search selects by ref, by type, with LIKE and with AND")
async def search(stack: Stack) -> None:
    by_type = f"component_type = '{NAVIGATION_URN}'"
    prefix = f"component_ref LIKE '{stack.engine_id}/%'"
    async with stack.session() as client:
        for condition in (ref_is(stack.navigation), by_type, f"{prefix} AND {by_type}"):
            result = await client.ok("rois.command.search", condition=condition)
            check(result["component_ref_list"] == [stack.navigation], f"{condition}: {result}")
        result = await client.ok("rois.command.search", condition=prefix)
        check(stack.navigation in result["component_ref_list"], f"{prefix}: {result}")
        bad = await client.call("rois.command.search", condition="nonsense !! 1")
        check(bad["return_code"] == "BAD_PARAMETER", f"bad condition: {bad}")


@scenario("C04", "a quote in a condition value survives")
async def quoted_value(stack: Stack) -> None:
    async with stack.session() as client:
        result = await client.ok("rois.command.search", condition=ref_is("it's/odd"))
        check(not result["component_ref_list"], f"matched: {result}")


@scenario("C05", "query answers, and is refused with no match or several")
async def query(stack: Stack) -> None:
    async with stack.session() as client:
        await client.ok(
            "rois.query.query", query_type="robot_position", condition=ref_is(stack.information)
        )
        none = await client.call("rois.query.query", query_type="no_such_query", condition="")
        check(none["return_code"] == "UNSUPPORTED", f"no match: {none}")
        several = await client.call(
            "rois.query.query", query_type="component_status", condition=""
        )
        check(several["return_code"] == "BAD_PARAMETER", f"several: {several}")
        await client.ok(
            "rois.query.query", query_type="component_status", condition=ref_is(stack.navigation)
        )


@scenario("C06", "an actuator takes one client, and a sensor is shared")
async def binds(stack: Stack) -> None:
    async with stack.session() as first, stack.session() as second:
        await first.ok("rois.command.bind", component_ref=stack.navigation)
        taken = await second.call("rois.command.bind", component_ref=stack.navigation)
        check(taken["return_code"] == "OUT_OF_RESOURCES", f"second bind: {taken}")
        by_condition = await second.call("rois.command.bind_any", condition=ref_is(stack.navigation))
        check(by_condition["return_code"] == "OUT_OF_RESOURCES", f"bind_any: {by_condition}")
        await first.ok("rois.command.bind", component_ref=stack.detection)
        await second.ok("rois.command.bind", component_ref=stack.detection)
        await first.ok("rois.command.release", component_ref=stack.navigation)
        result = await second.ok("rois.command.bind_any", condition=ref_is(stack.navigation))
        check(result["component_ref"] == stack.navigation, f"bind_any: {result}")


@scenario("C07", "a bind ends with its session")
async def bind_ends_with_session(stack: Stack) -> None:
    async with stack.session() as holder:
        await holder.ok("rois.command.bind", component_ref=stack.navigation)
    async with stack.session() as client:
        await client.ok("rois.command.bind", component_ref=stack.navigation)


@scenario("C08", "set_parameter applies and completes, and a bad value changes nothing")
async def set_parameter(stack: Stack) -> None:
    async with stack.session() as client:
        await client.ok("rois.command.bind", component_ref=stack.navigation)
        command_id = await stack.set_targets(client, '["kitchen"]')
        status = await client.completed(command_id, stack.event_timeout)
        check(status == "OK", f"set_parameter ended {status}")
        bad = await client.call(
            "rois.command.set_parameter",
            component_ref=stack.navigation,
            parameters=[
                {"name": "target_positions", "data_type_ref": "string[]", "value": "not json"}
            ],
        )
        check(bad["return_code"] == "BAD_PARAMETER", f"bad value: {bad}")
        result = await client.ok("rois.command.get_parameter", component_ref=stack.navigation)
        values = {p["name"]: p["value"] for p in result["parameters"]}
        check("kitchen" in values["target_positions"], f"parameters: {values}")
        await stack.set_targets(client, '["home"]')


@scenario("C09", "execute runs from bind to reached_target, with ids from the reply")
async def execute(stack: Stack) -> None:
    async with stack.session() as client:
        subscribed = await client.ok(
            "rois.event.subscribe", event_type="reached_target", condition=ref_is(stack.navigation)
        )
        await client.ok("rois.command.bind", component_ref=stack.navigation)
        [command_id] = await client.execute(
            {"component_ref": stack.navigation, "command_type": "start"}
        )
        status = await client.completed(command_id, stack.event_timeout)
        check(status == "OK", f"start ended {status}")
        await client.notification(
            NOTIFY_EVENT,
            lambda p: p["subscribe_id"] == subscribed["subscribe_id"],
            stack.event_timeout,
        )
        await client.ok("rois.command.get_command_result", command_id=command_id, condition="")


@scenario("C10", "a sequence with branches returns ids in order, branch by branch")
async def branches(stack: Stack) -> None:
    def branch(ref: str, command: str) -> Message:
        return {"command_list": [{"component_ref": ref, "command_type": command}]}

    async with stack.session() as client:
        await client.ok("rois.command.bind", component_ref=stack.navigation)
        await client.ok("rois.command.bind", component_ref=stack.detection)
        ids = await client.execute(
            {"component_ref": stack.detection, "command_type": "start"},
            {
                "branch_list": [
                    branch(stack.detection, "suspend"),
                    branch(stack.navigation, "suspend"),
                ]
            },
        )
        check(len(set(ids)) == 3, f"ids: {ids}")
        for command_id in ids:
            status = await client.completed(command_id, stack.event_timeout)
            check(status == "OK", f"{command_id} ended {status}")
        # A suspension outlives the bind, so stop the shared components for what follows.
        stopped = await client.execute(
            {"branch_list": [branch(stack.detection, "stop"), branch(stack.navigation, "stop")]}
        )
        for command_id in stopped:
            await client.completed(command_id, stack.event_timeout)


@scenario("C11", "a reply comes before its completion, which is never lost")
async def order(stack: Stack) -> None:
    async with stack.session() as client:
        await client.ok("rois.command.bind", component_ref=stack.navigation)
        for _ in range(ORDER_TRIES):
            start = len(client.messages)
            reply = await client.request(
                "rois.command.execute",
                {
                    "command_unit_list": [
                        {"component_ref": stack.navigation, "command_type": "stop"}
                    ]
                },
            )
            [command_id] = command_ids(reply["result"])
            head = client.messages[start : client.messages.index(reply, start)]
            check(
                not any(m.get("params", {}).get("command_id") == command_id for m in head),
                f"{command_id} completed before its reply",
            )
            await client.completed(command_id, stack.event_timeout)


@scenario("C12", "a failure aborts later items, and release aborts a running command")
async def aborts(stack: Stack) -> None:
    async with stack.session() as client:
        await client.ok("rois.command.bind", component_ref=stack.navigation)
        await stack.set_targets(client, "[]")
        failing, later = await client.execute(
            {"component_ref": stack.navigation, "command_type": "start"},
            {"component_ref": stack.navigation, "command_type": "stop"},
        )
        status = await client.completed(failing, stack.event_timeout)
        check(status == "ERROR", f"the failing command ended {status}")
        status = await client.completed(later, stack.event_timeout)
        check(status == "ABORT", f"the later command ended {status}")
        await stack.set_targets(client, '["home"]')
        [running] = await client.execute(
            {"component_ref": stack.navigation, "command_type": "start"}
        )
        await client.ok("rois.command.release", component_ref=stack.navigation)
        status = await client.completed(running, stack.event_timeout)
        check(status == "ABORT", f"the released command ended {status}")


@scenario("C13", "subscriptions are per client, and two clients can share an event")
async def subscriptions(stack: Stack) -> None:
    params = {"event_type": "person_detected", "condition": ref_is(stack.detection)}
    async with stack.session() as first, stack.session() as second:
        one = await first.ok("rois.event.subscribe", **params)
        again = await first.ok("rois.event.subscribe", **params)
        check(one["subscribe_id"] == again["subscribe_id"], "subscribing twice gave two ids")
        other = await second.ok("rois.event.subscribe", **params)
        check(one["subscribe_id"] != other["subscribe_id"], "two clients got one id")
        await first.ok("rois.event.unsubscribe", subscribe_id=f"{stack.engine_id}/sub-0")
        elsewhere = await first.call(
            "rois.event.subscribe",
            event_type="person_detected",
            condition=ref_is(stack.navigation),
        )
        check(elsewhere["return_code"] == "UNSUPPORTED", f"no such event: {elsewhere}")

        await first.notification(
            NOTIFY_EVENT, lambda p: p["subscribe_id"] == one["subscribe_id"], stack.event_timeout
        )
        await second.notification(
            NOTIFY_EVENT, lambda p: p["subscribe_id"] == other["subscribe_id"], stack.event_timeout
        )
        check(
            all(p["subscribe_id"] == other["subscribe_id"] for p in second.sent(NOTIFY_EVENT)),
            "a client received the events of another",
        )

        await first.ok("rois.event.unsubscribe", subscribe_id=one["subscribe_id"])
        left = len(first.sent(NOTIFY_EVENT))
        received = len(second.sent(NOTIFY_EVENT))
        await second.until(
            lambda: len(second.sent(NOTIFY_EVENT)) > received + 1,
            stack.event_timeout,
            "two events after the other client left",
        )
        check(len(first.sent(NOTIFY_EVENT)) == left, "events reached a client that unsubscribed")


@scenario("C14", "notify_event results equal get_event_detail")
async def event_detail(stack: Stack) -> None:
    async with stack.session() as client:
        await client.ok(
            "rois.event.subscribe", event_type="person_detected", condition=ref_is(stack.detection)
        )
        event = await client.notification(NOTIFY_EVENT, lambda _: True, stack.event_timeout)
        detail = await client.ok(
            "rois.event.get_event_detail", event_id=event["event_id"], condition=""
        )
        check(detail["results"] == event["results"], f"{detail} against {event}")


@scenario("C15", "notify_error reaches each holder, and get_error_detail reads it")
async def errors(stack: Stack) -> None:
    async with stack.session() as first, stack.session() as second:
        await first.ok("rois.command.bind", component_ref=stack.fault)
        await second.ok("rois.command.bind", component_ref=stack.fault)
        await first.execute({"component_ref": stack.fault, "command_type": "raise_error"})
        event = await first.notification(NOTIFY_ERROR, lambda _: True, stack.event_timeout)
        await second.notification(NOTIFY_ERROR, lambda _: True, stack.event_timeout)
        detail = await first.ok(
            "rois.system.get_error_detail", error_id=event["error_id"], condition=""
        )
        values = {r["name"]: r["value"] for r in detail["results"]}
        check(values.get("component_ref") == stack.fault, f"detail: {values}")

        async def cleared() -> bool:
            result = await first.call(
                "rois.system.get_error_detail", error_id=event["error_id"], condition=""
            )
            return bool(result["return_code"] == "BAD_PARAMETER")

        deadline = time.monotonic() + stack.event_timeout
        while not await cleared():
            check(time.monotonic() < deadline, "the error did not clear")
            await asyncio.sleep(0.1)


@scenario("C16", "profile_changed arrives when an engine joins and when it leaves")
async def profile_changed(stack: Stack) -> None:
    async with stack.session() as client:
        await client.ok("rois.command.bind", component_ref=stack.fault)
        await client.execute({"component_ref": stack.fault, "command_type": "peer_join"})
        await client.until(
            lambda: len(client.sent(PROFILE_CHANGED)) >= 2,
            stack.event_timeout,
            "second profile_changed",
        )


@scenario("C17", "a protocol fault answers a JSON-RPC error")
async def protocol_faults(stack: Stack) -> None:
    async with stack.session() as client:
        unknown = await client.request("rois.bogus")
        check(unknown.get("error", {}).get("code") == -32601, f"unknown method: {unknown}")
        invalid = await client.request("rois.command.execute", {"command_unit_list": []})
        check(invalid.get("error", {}).get("code") == -32602, f"invalid params: {invalid}")
        await client.connection.send("{not json")
        await client.until(
            lambda: any(m.get("error", {}).get("code") == -32700 for m in client.messages),
            stack.request_timeout,
            "parse error",
        )


@scenario("W02", "requests in parallel are answered by id")
async def parallel_requests(stack: Stack) -> None:
    async with stack.session() as client:
        results = await asyncio.gather(
            *[
                client.call("rois.query.query", query_type="robot_position",
                            condition=ref_is(stack.information))
                for _ in range(30)
            ],
            *[client.call("rois.command.search", condition="") for _ in range(30)],
        )
        check(all(r["return_code"] == "OK" for r in results), "a parallel request failed")


@scenario("W03", "a message over 1 MiB closes the connection with 1009")
async def message_limit(stack: Stack) -> None:
    async with stack.session() as client:
        with_limit = "x" * TOO_LARGE
        await client.connection.send(
            json.dumps({"jsonrpc": "2.0", "id": 0, "method": "rois.command.search",
                        "params": {"condition": with_limit}})
        )
        await client.until(
            lambda: client.close_code is not None, stack.request_timeout, "close"
        )
        check(client.close_code == 1009, f"closed with {client.close_code}")


async def wait_for_stack(stack: Stack, timeout: float) -> None:
    """Retry until the gateway answers and lists the components of the mock adapter."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            async with stack.session() as client:
                result = await client.call("rois.command.search", condition="")
                if stack.fault in result.get("component_ref_list", []):
                    return
        except (OSError, TimeoutError, InvalidHandshake, ConnectionClosed, CheckFailed):
            pass
        check(time.monotonic() < deadline, f"{stack.fault} did not appear at {stack.url}")
        await asyncio.sleep(0.5)


async def run_list(stack: Stack, timeout: float) -> int:
    """Run every scenario and return the exit code."""
    await wait_for_stack(stack, timeout)
    failed = 0
    for scenario_id, title, function in SCENARIOS:
        try:
            await function(stack)
            print(f"ok   {scenario_id} {title}")
        except (CheckFailed, OSError, TimeoutError, ConnectionClosed) as exc:
            failed += 1
            print(f"FAIL {scenario_id} {title}: {exc or type(exc).__name__}")
    print(f"{len(SCENARIOS) - failed} of {len(SCENARIOS)} scenarios passed")
    return 1 if failed else 0


async def watch_close(stack: Stack) -> int:
    """Hold one connection until the gateway closes it, and return the exit code."""
    async with stack.session() as client:
        await client.until(lambda: client.close_code is not None, 3600.0, "close")
        print(f"The gateway closed the connection with code {client.close_code}.")
        return 0 if client.close_code == 1001 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--url", default="ws://127.0.0.1:8765")
    parser.add_argument("--engine-id", default="mock", help="engine id of the mock adapter")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for the stack")
    parser.add_argument("--event-timeout", type=float, default=20.0)
    parser.add_argument("--watch-close", action="store_true")
    args = parser.parse_args()
    stack = Stack(args.url, args.engine_id, args.event_timeout)
    try:
        code = asyncio.run(
            watch_close(stack) if args.watch_close else run_list(stack, args.timeout)
        )
    except CheckFailed as exc:
        print(f"FAIL {exc}")
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
