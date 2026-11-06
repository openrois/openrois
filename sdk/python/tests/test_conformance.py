"""The conformance list of testing/conformance/README.md, one test per scenario.

Each test has the id of its scenario in its name. The tests at the end of this file need no
stack: they fail when an id of the list has no test here, when a test has no id in the list,
and when a method of the catalog has no client member.

The scenarios use only the public surface and take only URLs. Every fault comes from a RoIS
call on ``mock/fault`` or from a path of the scripted server, which a fixture starts. W01 to
W03 stay with testing/conformance/wire_check.py, because a client SDK cannot reach them.

C01 to C17 run when OPENROIS_GATEWAY_URL names a gateway with the mock adapter behind it, and
are skipped otherwise. C18 to C21 need only the scripted server, so they always run:

    OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 pytest tests/test_conformance.py

OPENROIS_MOCK_ENGINE_ID names the engine of the mock adapter, ``mock`` by default.
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from openrois.interfaces import (
    METHODS_BY_NAME,
    CompletedParams,
    NotifyErrorParams,
    NotifyEventParams,
    ProfileChangedParams,
    ReturnCode,
    RoISIdentifierType,
)

from openrois.sdk import (
    COMPONENT_REF,
    RoISClient,
    RoISConnectionError,
    RoISError,
    RpcError,
    TransportError,
    all_of,
    component_ref,
    component_type,
    like,
    quote,
)

README = Path(__file__).parents[3] / "testing" / "conformance" / "README.md"
SUITE = Path(__file__)

ENGINE_ID = os.environ.get("OPENROIS_MOCK_ENGINE_ID", "mock")

DETECTION = f"{ENGINE_ID}/person_detection"
NAVIGATION = f"{ENGINE_ID}/navigation"
INFORMATION = f"{ENGINE_ID}/system_information"
FAULT = f"{ENGINE_ID}/fault"

#: The longest wait in seconds for one notification, enough for a detection at full time scale.
WAIT = 20.0

#: The longest wait in seconds for the stack to come up.
STACK_WAIT = 60.0

#: How many commands the scenario on lost completions runs.
COMPLETION_ROUNDS = 100

#: How many parameter changes it runs, which take longer than a command.
PARAMETER_ROUNDS = 5


class Session:
    """A client and every notification it received since it connected.

    This is the recipe of the SDK README: the listener is there before the call whose ids it
    records.
    """

    def __init__(self, client: RoISClient) -> None:
        self.client = client
        self.completed: list[CompletedParams] = []
        self.events: list[NotifyEventParams] = []
        self.errors: list[NotifyErrorParams] = []
        self.profile_changes: list[ProfileChangedParams] = []
        self._waiting: set[asyncio.Event] = set()
        client.on("rois.command.completed", partial(self._record, self.completed))
        client.on("rois.event.notify_event", partial(self._record, self.events))
        client.on("rois.system.notify_error", partial(self._record, self.errors))
        client.on("rois.system.profile_changed", partial(self._record, self.profile_changes))

    def _record[T](self, received: list[T], params: T) -> None:
        received.append(params)
        for arrived in self._waiting:
            arrived.set()

    async def _until[T](self, find: Callable[[], T | None], received: list[Any]) -> T:
        """Wait until ``find`` returns something, looking again at each notification."""
        arrived = asyncio.Event()
        self._waiting.add(arrived)
        try:
            async with asyncio.timeout(WAIT):
                while (found := find()) is None:
                    await arrived.wait()
                    arrived.clear()
                return found
        except TimeoutError:
            pytest.fail(f"Nothing new within {WAIT} s, after {received}")
        finally:
            self._waiting.discard(arrived)

    async def seen[T](self, received: list[T], match: Callable[[T], bool] = lambda _: True) -> T:
        """The first notification of a list that matches, waiting for it if needed."""
        return await self._until(lambda: next(filter(match, received), None), received)

    async def beyond(self, received: list[Any], count: int) -> None:
        """Wait until a list holds more than ``count`` notifications."""
        await self._until(lambda: True if len(received) > count else None, received)

    async def completion(self, command_id: str) -> str:
        """Wait until a command completes, and return its status."""
        params = await self.seen(self.completed, lambda p: p.command_id == command_id)
        return params.status


@asynccontextmanager
async def session(url: str) -> AsyncIterator[Session]:
    """Run a session on a new client, and close it however the session ends."""
    async with RoISClient.connect(url) as client:
        yield Session(client)


async def refused(call: Awaitable[object], return_code: ReturnCode) -> None:
    """Expect a call to fail with a RoIS return code."""
    with pytest.raises(RoISError) as caught:
        await call
    assert caught.value.return_code is return_code


def close_of(client: RoISClient) -> asyncio.Future[tuple[int, str]]:
    """What a client reports when its connection closes."""
    closed: asyncio.Future[tuple[int, str]] = asyncio.get_running_loop().create_future()
    client.on("close", lambda code, reason: closed.set_result((code, reason)))
    return closed


def targets(value: str) -> list[dict[str, str]]:
    """The target_positions parameter of the navigation."""
    return [{"name": "target_positions", "data_type_ref": "string[]", "value": value}]


def echo(text: str) -> dict[str, Any]:
    """A command that gives its text back as a result, which tells it from any other."""
    return {
        "component_ref": FAULT,
        "command_type": "echo",
        "arguments": [{"name": "text", "data_type_ref": "string", "value": text}],
    }


def end_with(status: str) -> dict[str, Any]:
    """A command that ends with a chosen status."""
    return {
        "component_ref": FAULT,
        "command_type": "end_with",
        "arguments": [{"name": "status", "data_type_ref": "string", "value": status}],
    }


async def stack_is_up(url: str) -> bool:
    """Whether the stack answers and the mock adapter has joined it."""
    try:
        async with session(url) as live:
            return FAULT in await live.client.search()
    except (RoISError, TransportError):
        return False


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def gateway_url() -> str:
    """The gateway with the mock adapter behind it, once that adapter has joined.

    A scenario that takes it is skipped when no stack was named. The stack may still be
    starting when the run begins, so this waits for it.
    """
    url = os.environ.get("OPENROIS_GATEWAY_URL", "")
    if url == "":
        pytest.skip("OPENROIS_GATEWAY_URL names no gateway")
    try:
        async with asyncio.timeout(STACK_WAIT):
            while not await stack_is_up(url):
                await asyncio.sleep(0.5)
    except TimeoutError:
        pytest.fail(f"{FAULT} did not appear at {url}")
    return url


async def test_c01_disconnect_is_safe_twice_and_a_later_call_fails_locally(
    gateway_url: str,
) -> None:
    client = await RoISClient.connect(gateway_url)
    closed: list[int] = []
    client.on("close", lambda code, _reason: closed.append(code))

    await client.disconnect()
    await client.disconnect()

    assert closed == [1000]
    with pytest.raises(TransportError, match="not connected"):
        await client.search()

    # The block ends while both calls are in flight, so its own disconnect overlaps them.
    async with RoISClient.connect(gateway_url) as overlapped:
        calls = asyncio.gather(overlapped.disconnect(), overlapped.disconnect())
    await calls
    with pytest.raises(TransportError, match="not connected"):
        await overlapped.search()


async def test_c02_get_profile_lists_the_sub_profile_and_each_component_profile(
    gateway_url: str,
) -> None:
    async with session(gateway_url) as live:
        engine = await live.client.get_profile()
        assert ENGINE_ID in [sub.identifier.code for sub in engine.profile.sub_profiles]
        assert {DETECTION, NAVIGATION, INFORMATION, FAULT} <= engine.component_profiles.keys()
        navigation = engine.component_profiles[NAVIGATION]
        assert navigation.function == "actuation"
        assert [command.name for command in navigation.command_profiles] == [
            "start",
            "stop",
            "suspend",
            "resume",
        ]


async def test_c03_search_selects_by_ref_by_type_with_like_and_with_and(gateway_url: str) -> None:
    by_type = component_type(RoISIdentifierType(authority="OMG", code="Navigation"))
    prefix = like(COMPONENT_REF, f"{ENGINE_ID}/%")
    async with session(gateway_url) as live:
        client = live.client
        assert await client.search(component_ref(NAVIGATION)) == [NAVIGATION]
        assert await client.search(by_type) == [NAVIGATION]
        assert await client.search(all_of(prefix, by_type)) == [NAVIGATION]
        # Each term matches alone, so an empty answer shows that both were applied.
        assert await client.search(component_ref(DETECTION)) == [DETECTION]
        assert await client.search(all_of(component_ref(DETECTION), by_type)) == []
        assert {DETECTION, NAVIGATION, INFORMATION, FAULT} <= set(await client.search(prefix))
        await refused(client.search("nonsense !! 1"), ReturnCode.BAD_PARAMETER)


async def test_c04_a_quote_in_a_condition_value_survives_the_builders(gateway_url: str) -> None:
    async with session(gateway_url) as live:
        assert quote("it's") == "'it''s'"
        # A quote that reached the engine unescaped would end the literal early, and the
        # engine would answer BAD_PARAMETER where these find nothing.
        assert await live.client.search(component_ref("it's/odd")) == []
        assert await live.client.search(like(COMPONENT_REF, "it's%")) == []


async def test_c05_query_follows_its_condition(gateway_url: str) -> None:
    async with session(gateway_url) as live:
        client = live.client
        position = await client.query("robot_position", component_ref(INFORMATION))
        assert [result.name for result in position] == ["position_data", "robot_ref", "timestamp"]
        await refused(client.query("no_such_query"), ReturnCode.UNSUPPORTED)
        await refused(client.query("component_status"), ReturnCode.BAD_PARAMETER)
        # Several components declare this query, so only the condition can make it answer.
        status = await client.query("component_status", component_ref(NAVIGATION))
        assert "status" in [result.name for result in status]


async def test_c06_an_actuator_refuses_a_second_client_and_a_sensor_is_shared(
    gateway_url: str,
) -> None:
    async with session(gateway_url) as one, session(gateway_url) as two:
        first, second = one.client, two.client
        await first.bind(NAVIGATION)
        await refused(second.bind(NAVIGATION), ReturnCode.OUT_OF_RESOURCES)
        await refused(second.bind_any(component_ref(NAVIGATION)), ReturnCode.OUT_OF_RESOURCES)

        await first.bind(DETECTION)
        await second.bind(DETECTION)

        await first.release(NAVIGATION)
        assert await second.bind_any(component_ref(NAVIGATION)) == NAVIGATION


async def test_c07_a_bind_ends_with_its_session(gateway_url: str) -> None:
    async with session(gateway_url) as live:
        await live.client.bind(NAVIGATION)
    async with session(gateway_url) as live:
        await live.client.bind(NAVIGATION)


async def test_c08_set_parameter_applies_and_a_bad_value_changes_nothing(
    gateway_url: str,
) -> None:
    async with session(gateway_url) as live:
        client = live.client
        await client.bind(NAVIGATION)
        applied = await client.set_parameter(NAVIGATION, targets('["kitchen"]'))
        assert await live.completion(applied) == "OK"

        await refused(
            client.set_parameter(NAVIGATION, targets("not json")), ReturnCode.BAD_PARAMETER
        )

        parameters = await client.get_parameter(NAVIGATION)
        assert "kitchen" in {p.name: p.value for p in parameters}["target_positions"]
        await live.completion(await client.set_parameter(NAVIGATION, targets('["home"]')))


async def test_c09_execute_runs_from_bind_to_reached_target(gateway_url: str) -> None:
    async with session(gateway_url) as live:
        client = live.client
        await client.bind(NAVIGATION)
        await live.completion(await client.set_parameter(NAVIGATION, targets('["kitchen"]')))
        subscribe_id = await client.subscribe("reached_target", component_ref(NAVIGATION))

        [command_id] = await client.execute(
            [{"component_ref": NAVIGATION, "command_type": "start"}]
        )

        assert await live.completion(command_id) == "OK"
        event = await live.seen(live.events, lambda e: e.subscribe_id == subscribe_id)
        assert event.event_type == "reached_target"
        assert {r.name: r.value for r in event.results}["target"] == "kitchen"
        assert await client.get_command_result(command_id) == []
        await live.completion(await client.set_parameter(NAVIGATION, targets('["home"]')))


async def test_c10_a_sequence_with_branches_returns_ids_in_order(gateway_url: str) -> None:
    async with session(gateway_url) as live:
        client = live.client
        await client.bind(FAULT)

        ids = await client.execute(
            [
                echo("first"),
                {
                    "branch_list": [
                        {"command_list": [echo("left one"), echo("left two")]},
                        {"command_list": [echo("right")]},
                    ]
                },
                echo("last"),
            ]
        )

        assert [await live.completion(command_id) for command_id in ids] == ["OK"] * 5
        # Each command gives back its own text, so the ids must name them in this order.
        results = [await client.get_command_result(command_id) for command_id in ids]
        assert [text.value for [text] in results] == [
            "first",
            "left one",
            "left two",
            "right",
            "last",
        ]


async def test_c11_a_listener_added_first_sees_every_completion(gateway_url: str) -> None:
    async with session(gateway_url) as live:
        client = live.client
        await client.bind(NAVIGATION)
        ids: list[str] = []
        for _ in range(COMPLETION_ROUNDS):
            [command_id] = await client.execute(
                [{"component_ref": NAVIGATION, "command_type": "stop"}]
            )
            ids.append(command_id)
            assert await live.completion(command_id) == "OK"
        for _ in range(PARAMETER_ROUNDS):
            command_id = await client.set_parameter(NAVIGATION, targets('["home"]'))
            ids.append(command_id)
            assert await live.completion(command_id) == "OK"
        assert [completed.command_id for completed in live.completed] == ids


async def test_c12_a_command_ending_badly_aborts_the_later_items(gateway_url: str) -> None:
    async with session(gateway_url) as live:
        client = live.client
        await client.bind(FAULT)
        [failing, later, last] = await client.execute(
            [end_with("ERROR"), echo("never runs"), echo("never runs either")]
        )
        assert await live.completion(failing) == "ERROR"
        assert await live.completion(later) == "ABORT"
        assert await live.completion(last) == "ABORT"

        await client.bind(NAVIGATION)
        [running] = await client.execute([{"component_ref": NAVIGATION, "command_type": "start"}])
        await client.release(NAVIGATION)
        assert await live.completion(running) == "ABORT"


async def test_c13_events_reach_only_their_subscriber_and_two_clients_stay_apart(
    gateway_url: str,
) -> None:
    condition = component_ref(DETECTION)
    async with session(gateway_url) as first, session(gateway_url) as second:
        one = await first.client.subscribe("person_detected", condition)
        assert await first.client.subscribe("person_detected", condition) == one
        other = await second.client.subscribe("person_detected", condition)
        assert other != one
        await first.client.unsubscribe(f"{ENGINE_ID}/sub-0")
        # This condition selects a component without the event, which only a condition that
        # reaches the engine can refuse. No event of the mock adapter is declared twice, so
        # the refusal is what shows it here.
        await refused(
            first.client.subscribe("person_detected", component_ref(NAVIGATION)),
            ReturnCode.UNSUPPORTED,
        )

        await first.seen(first.events, lambda e: e.subscribe_id == one)
        await second.seen(second.events, lambda e: e.subscribe_id == other)
        assert all(event.subscribe_id == one for event in first.events)
        assert all(event.subscribe_id == other for event in second.events)

        # One client leaves by unsubscribing. Two more events prove the other still receives
        # them while the one that left does not, because a reply and the events around it
        # arrive in order on one socket.
        await first.client.unsubscribe(one)
        left = len(first.events)
        await second.beyond(second.events, len(second.events) + 1)
        assert len(first.events) == left

        # Then it leaves by ending its session.
        await first.client.subscribe("person_detected", condition)
        await first.client.disconnect()
        await second.beyond(second.events, len(second.events))


async def test_c14_notify_event_results_equal_get_event_detail(gateway_url: str) -> None:
    async with session(gateway_url) as live:
        await live.client.subscribe("person_detected", component_ref(DETECTION))
        event = await live.seen(live.events)
        assert [result.name for result in event.results] == ["number", "timestamp"]
        assert await live.client.get_event_detail(event.event_id) == event.results


async def test_c15_notify_error_reaches_each_holder_and_get_error_detail_reads_it(
    gateway_url: str,
) -> None:
    async with session(gateway_url) as first, session(gateway_url) as second:
        await first.client.bind(FAULT)
        await second.client.bind(FAULT)
        await first.client.execute([{"component_ref": FAULT, "command_type": "raise_error"}])

        error_id = (await first.seen(first.errors)).error_id
        await second.seen(second.errors, lambda e: e.error_id == error_id)
        detail = await first.client.get_error_detail(error_id)
        assert {r.name: r.value for r in detail}["component_ref"] == FAULT

        async def cleared() -> bool:
            try:
                await first.client.get_error_detail(error_id)
            except RoISError as error:
                return error.return_code is ReturnCode.BAD_PARAMETER
            return False

        # The error clears by itself, and the scenarios after this one need the component.
        async with asyncio.timeout(WAIT):
            while not await cleared():
                await asyncio.sleep(0.1)


async def test_c16_profile_changed_arrives_when_an_engine_joins_and_leaves(
    gateway_url: str,
) -> None:
    async def has_peer(client: RoISClient) -> bool:
        engine = await client.get_profile()
        return "mock_peer" in [sub.identifier.code for sub in engine.profile.sub_profiles]

    async with session(gateway_url) as live:
        client = live.client
        await client.bind(FAULT)
        assert not await has_peer(client)

        await client.execute([{"component_ref": FAULT, "command_type": "peer_join"}])

        await live.beyond(live.profile_changes, 0)
        assert await has_peer(client)
        await live.beyond(live.profile_changes, 1)
        assert not await has_peer(client)


async def test_c17_method_not_found_through_the_raw_send_is_an_rpc_error(
    gateway_url: str,
) -> None:
    async with session(gateway_url) as live:
        with pytest.raises(RpcError) as caught:
            await live.client.transport.send("rois.bogus")
        assert caught.value.code == -32601
        assert await live.client.search(component_ref(NAVIGATION)) == [NAVIGATION]


async def test_c18_replies_in_reverse_order_reach_the_right_callers(scripted_url: str) -> None:
    async with RoISClient.connect(f"{scripted_url}/reverse") as client:
        answered: list[str] = []

        async def ask(condition: str) -> list[str]:
            refs = await client.search(condition)
            answered.append(condition)
            return refs

        replies = await asyncio.gather(ask("one"), ask("two"), ask("three"))

        assert list(replies) == [["one"], ["two"], ["three"]]
        assert answered == ["three", "two", "one"]


async def test_c19_a_malformed_message_reaches_the_error_listener(scripted_url: str) -> None:
    async with RoISClient.connect(f"{scripted_url}/malformed") as client:
        errors: list[Exception] = []
        client.on("error", errors.append)

        assert await client.search("before") == ["before"]

        assert len(errors) == 2
        assert all(isinstance(error, TransportError) for error in errors)
        assert await client.search("after") == ["after"]


async def test_c20_a_dropped_connection_fails_pending_requests_and_fires_close(
    scripted_url: str,
) -> None:
    async with RoISClient.connect(f"{scripted_url}/drop") as client:
        closed = close_of(client)

        calls = await asyncio.gather(
            client.search("one"),
            client.search("two"),
            client.search("three"),
            return_exceptions=True,
        )

        assert all(isinstance(call, RoISConnectionError) for call in calls)
        code, _reason = await asyncio.wait_for(closed, WAIT)
        assert code == 1006
        with pytest.raises(TransportError):
            await client.search()


async def test_c21_a_server_close_reaches_close_with_its_code_and_reason(
    scripted_url: str,
) -> None:
    async with RoISClient.connect(f"{scripted_url}/close-1001") as client:
        closed = close_of(client)

        assert await client.search("only") == ["only"]

        assert await asyncio.wait_for(closed, WAIT) == (1001, "scripted close")


def listed_ids() -> list[str]:
    """The ids in the table under "## The List" that a client SDK has to run."""
    section = README.read_text().split("\n## The List\n")[1].split("\n## ")[0]
    return re.findall(r"^\| (C\d+) \|", section, re.MULTILINE)


def ids_with_a_test() -> list[str]:
    """The id at the start of each test name in this file."""
    return [
        id_.upper()
        for id_ in re.findall(r"^(?:async )?def test_(c\d+)_", SUITE.read_text(), re.MULTILINE)
    ]


def test_the_list_can_be_read() -> None:
    assert "C01" in listed_ids()


def test_each_id_of_the_list_has_one_test() -> None:
    assert ids_with_a_test() == listed_ids()


def test_the_scenarios_import_only_the_public_surface() -> None:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(SUITE.read_text())):
        if isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    assert {name for name in modules if name.startswith(("openrois", "websockets"))} == {
        "openrois.interfaces",
        "openrois.sdk",
    }


@pytest.mark.parametrize("method", sorted(METHODS_BY_NAME))
def test_the_client_has_a_member_for(method: str) -> None:
    # connect is a class method, because it is the one operation that makes a client.
    assert callable(getattr(RoISClient, method.rsplit(".", 1)[-1], None))
