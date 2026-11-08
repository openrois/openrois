"""Tests of the session against a fake engine with binds."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from openrois.interfaces import ProfileChangedParams, ReturnCode
from openrois.sdk import RoISError

from openrois.mcp import session as session_module
from openrois.mcp.config import Settings
from openrois.mcp.session import AgentError, Session, rois_failure
from tests.fakes import Engine, factory_for

NAV = "robot/navigation"
PEOPLE = "robot/person_detection"


def make(engine: Engine, **settings: Any) -> Session:
    options: dict[str, Any] = {"allow_actions": True, "command_timeout": 1.0, **settings}
    return Session(Settings(**options), factory_for(engine))


def failure(caught: pytest.ExceptionInfo[AgentError]) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(str(caught.value))
    return parsed


async def test_the_session_opens_on_the_first_call() -> None:
    engine = Engine()
    session = make(engine)
    assert engine.sessions == []
    listed = await session.list_components()
    assert len(engine.sessions) == 1
    refs = [component["ref"] for component in listed["components"]]
    assert refs == [NAV, PEOPLE]
    assert listed["components"][0]["component_status"] == "READY"


async def test_run_commands_needs_a_bind_by_default() -> None:
    session = make(Engine())
    with pytest.raises(AgentError) as caught:
        await session.run_commands([{"component_ref": NAV, "command_type": "start"}])
    assert failure(caught) == {
        "step": "bind",
        "component_ref": NAV,
        "return_code": "NOT_BOUND",
        "hint": "not bound by this session, call bind first",
    }


async def test_bind_then_run_reports_how_each_command_ended() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    result = await session.run_commands(
        [
            {"component_ref": NAV, "command_type": "go", "arguments": {"speed": 0.5}},
            {"branch_list": [[{"component_ref": NAV, "command_type": "stop"}]], "delay_time": 10},
        ]
    )
    assert [command["status"] for command in result["commands"]] == ["OK", "OK"]
    sent = engine.executed[0]
    assert sent[0]["arguments"] == [{"name": "speed", "data_type_ref": "double", "value": "0.5"}]
    assert sent[1] == {
        "branch_list": [{"command_list": [{"component_ref": NAV, "command_type": "stop"}]}],
        "delay_time": 10,
    }


async def test_a_command_still_running_reads_running() -> None:
    engine = Engine()
    engine.outcome["start"] = None
    session = make(engine)
    await session.bind(NAV)
    result = await session.run_commands(
        [{"component_ref": NAV, "command_type": "start"}], timeout=0.05
    )
    assert result["commands"][0]["status"] == "RUNNING"
    assert session.state()["running_commands"][0]["command_type"] == "start"


async def test_without_wait_run_commands_returns_the_ids() -> None:
    session = make(Engine())
    await session.bind(NAV)
    result = await session.run_commands(
        [{"component_ref": NAV, "command_type": "start"}], wait=False
    )
    assert "commands" not in result
    await asyncio.sleep(0)
    assert (await session.command_status(result["command_ids"]))["commands"][0]["status"] == "OK"


async def test_an_unknown_command_names_the_declared_ones() -> None:
    session = make(Engine())
    await session.bind(NAV)
    with pytest.raises(AgentError, match="commands: go, start, stop"):
        await session.run_commands([{"component_ref": NAV, "command_type": "fly"}])


async def test_auto_bind_is_all_or_nothing() -> None:
    engine = Engine()
    other = make(engine)
    await other.bind(NAV)
    session = make(engine)
    with pytest.raises(AgentError) as caught:
        await session.run_commands(
            [
                {"component_ref": PEOPLE, "command_type": "start"},
                {"component_ref": NAV, "command_type": "start"},
            ],
            auto_bind=True,
        )
    # PEOPLE has no start command, so the call fails before any bind.
    assert "BAD_PARAMETER" in str(caught.value)

    # With two valid commands, the first bind succeeds and is undone when the second fails.
    from tests import fakes

    fakes.PEOPLE.command_profiles.append(fakes.NAVIGATION.command_profiles[0])
    try:
        with pytest.raises(AgentError) as caught:
            await session.run_commands(
                [
                    {"component_ref": PEOPLE, "command_type": "start"},
                    {"component_ref": NAV, "command_type": "start"},
                ],
                auto_bind=True,
            )
    finally:
        fakes.PEOPLE.command_profiles.pop()
    assert failure(caught)["return_code"] == "OUT_OF_RESOURCES"
    assert failure(caught)["component_ref"] == NAV
    assert "another session holds this component" in failure(caught)["hint"]
    assert session.state()["binds"] == []
    assert (2, PEOPLE) in engine.released
    assert engine.executed == []


async def test_auto_bind_binds_and_keeps_the_binds() -> None:
    session = make(Engine())
    result = await session.run_commands(
        [{"component_ref": NAV, "command_type": "start"}], auto_bind=True
    )
    assert result["bound_by_this_call"] == [NAV]
    assert session.state()["binds"] == [NAV]


async def test_a_busy_component_fails_to_bind_and_reads_busy() -> None:
    engine = Engine()
    holder = make(engine)
    await holder.bind(NAV)
    session = make(engine)
    with pytest.raises(AgentError) as caught:
        await session.bind(NAV)
    assert failure(caught)["return_code"] == "OUT_OF_RESOURCES"
    # The agent asks the user before it waits for another client's component.
    assert "ask whether to wait" in failure(caught)["hint"]
    listed = await session.list_components()
    assert listed["components"][0]["component_status"] == "BUSY"
    assert listed["components"][0]["held_by_this_session"] is False
    # A sensing component takes a bind per session, so both hold it.
    await holder.bind(PEOPLE)
    await session.bind(PEOPLE)


async def test_bind_waits_for_a_release() -> None:
    engine = Engine()
    holder = make(engine)
    await holder.bind(NAV)
    session = make(engine, command_timeout=5.0)

    async def release_soon() -> None:
        await asyncio.sleep(0.2)
        await holder.release(NAV)

    task = asyncio.create_task(release_soon())
    result = await session.bind(NAV, wait_seconds=3)
    await task
    assert result["bound"] is True


async def test_the_allow_filter_limits_actions_but_not_discovery() -> None:
    session = make(Engine(), allow=("robot/person_%",))
    with pytest.raises(AgentError) as caught:
        await session.bind(NAV)
    assert failure(caught)["return_code"] == "NOT_ALLOWED"
    listed = await session.list_components()
    assert len(listed["components"]) == 2
    assert [c["actions_allowed"] for c in listed["components"]] == [False, True]
    await session.bind(PEOPLE)


async def test_set_parameters_types_values_and_waits() -> None:
    session = make(Engine())
    await session.bind(NAV)
    result = await session.set_parameters(NAV, {"target_positions": ["kitchen"]})
    assert result["status"] == "OK"
    with pytest.raises(AgentError, match="BAD_PARAMETER: parameter time_limit"):
        await session.set_parameters(NAV, {"time_limit": "soon"})


async def test_get_parameters_of_a_sensor_needs_no_bind() -> None:
    engine = Engine()
    session = make(engine)
    result = await session.get_parameters(PEOPLE)
    assert result["parameters"] == [{"name": "threshold", "type": "double", "value": 0.5}]
    assert session.state()["binds"] == []
    with pytest.raises(AgentError, match="Call bind first"):
        await session.get_parameters(NAV)


async def test_get_parameters_does_not_bind_in_a_read_only_server() -> None:
    engine = Engine()
    with pytest.raises(AgentError, match="this server is read-only"):
        await make(engine, allow_actions=False).get_parameters(PEOPLE)
    with pytest.raises(AgentError, match="acts only on components matching"):
        await make(engine, allow=("robot/nav%",)).get_parameters(PEOPLE)
    assert engine.released == []
    assert engine.holders[PEOPLE] == set()


async def test_get_parameters_and_a_bind_at_once_keep_the_bind() -> None:
    engine = Engine()
    session = make(engine)
    await asyncio.gather(session.get_parameters(PEOPLE), session.bind(PEOPLE))
    assert session.state()["binds"] == [PEOPLE]
    # The temporary release of get_parameters did not take the bind away.
    assert engine.holders[PEOPLE] == {1}


async def test_release_reports_the_commands_it_aborts() -> None:
    engine = Engine()
    engine.outcome["start"] = None
    session = make(engine)
    await session.bind(NAV)
    started = await session.run_commands(
        [{"component_ref": NAV, "command_type": "start"}], wait=False
    )
    released = await session.release(NAV)
    assert released["aborted_command_ids"] == started["command_ids"]
    assert "still_running_command_ids" not in released


async def test_release_reports_only_the_commands_that_ended_abort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_module, "RELEASE_SETTLE", 0.05)
    engine = Engine()
    engine.outcome["start"] = None
    engine.outcome["stop"] = None
    session = make(engine)
    await session.bind(NAV)
    started = await session.run_commands(
        [
            {"component_ref": NAV, "command_type": "start"},
            {"component_ref": NAV, "command_type": "stop"},
        ],
        wait=False,
    )
    running, waiting = started["command_ids"]
    # The engine aborts the running command, but the one waiting its turn survives.
    engine.queued.add(waiting)
    released = await session.release(NAV)
    assert released["aborted_command_ids"] == [running]
    assert released["still_running_command_ids"] == [waiting]
    assert "may still run" in released["hint"]


async def test_events_reach_the_buffer_with_their_component() -> None:
    engine = Engine()
    session = make(engine)
    subscribed = await session.subscribe(PEOPLE, "person_detected")
    client = engine.sessions[0]

    async def fire_soon() -> None:
        await asyncio.sleep(0.01)
        client.fire(subscribed["subscribe_id"], 2)

    task = asyncio.create_task(fire_soon())
    waited = await session.wait_for_event("person_detected", PEOPLE, timeout=1)
    await task
    assert waited["timed_out"] is False
    assert waited["entry"]["component_ref"] == PEOPLE
    assert waited["entry"]["results"] == [{"name": "number", "type": "int", "value": 2}]
    read = session.get_events(since=subscribed["cursor"])
    assert [entry["kind"] for entry in read["entries"]] == ["event"]


async def test_wait_for_event_times_out() -> None:
    session = make(Engine())
    assert (await session.wait_for_event(timeout=0.01))["timed_out"] is True


async def test_shutdown_stops_what_the_session_started() -> None:
    engine = Engine()
    session = make(engine)
    subscribed = await session.subscribe(PEOPLE, "person_detected")
    await session.run_commands([{"component_ref": NAV, "command_type": "start"}], auto_bind=True)
    await session.shutdown()
    client = engine.sessions[0]
    assert engine.executed[-1] == [
        {
            "branch_list": [
                {"command_list": [{"component_ref": NAV, "command_type": "stop"}]},
            ]
        }
    ]
    assert client.unsubscribed == [subscribed["subscribe_id"]]
    assert (1, NAV) in engine.released
    assert client.disconnected


async def test_a_stop_after_the_start_needs_no_stop_at_shutdown() -> None:
    engine = Engine()
    session = make(engine)
    await session.run_commands(
        [
            {"component_ref": NAV, "command_type": "start"},
            {"component_ref": NAV, "command_type": "stop"},
        ],
        auto_bind=True,
    )
    await session.shutdown()
    assert len(engine.executed) == 1


async def test_shutdown_gives_up_on_a_gateway_that_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_module, "SHUTDOWN_TIMEOUT", 0.1)
    engine = Engine()
    session = make(engine)
    await session.run_commands([{"component_ref": NAV, "command_type": "start"}], auto_bind=True)
    engine.hang_execute = True
    loop = asyncio.get_running_loop()
    began = loop.time()
    await session.shutdown()
    assert loop.time() - began < 1.0
    assert engine.sessions[0].disconnected


async def test_shutdown_releases_every_bind_and_disconnects() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    await session.bind(PEOPLE)
    await session.shutdown()
    client = engine.sessions[0]
    assert {ref for _, ref in engine.released} == {NAV, PEOPLE}
    assert client.disconnected
    assert engine.holders[NAV] == set()


async def test_a_lost_connection_is_reported_and_reopened() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    engine.sessions[0].drop()
    assert session.state()["binds"] == []
    read = session.get_events()
    assert read["entries"][-1]["kind"] == "connection_closed"
    assert "binds, subscriptions and running commands" in read["notice"]
    listed = await session.list_components()
    # The notice was delivered once.
    assert "notice" not in listed
    assert len(engine.sessions) == 2


async def test_idle_binds_are_released_when_asked() -> None:
    engine = Engine()
    session = make(engine, idle_release=0.1)
    await session.bind(NAV)
    found = await session.events.wait_for(0, lambda entry: entry.kind == "idle_release", 2.0)
    assert found is not None and found.data["component_ref"] == NAV
    assert session.state()["binds"] == []
    await session.shutdown()


async def test_rois_errors_name_the_method_and_a_hint() -> None:
    session = make(Engine())
    with pytest.raises(AgentError, match="rois.query.query returned UNSUPPORTED for robot"):
        await session.query(NAV, "battery")
    engine = Engine()
    engine.fail_bind[NAV] = ReturnCode.ERROR
    with pytest.raises(AgentError) as caught:
        await make(engine).bind(NAV)
    assert failure(caught)["return_code"] == "ERROR"


# -- Binds and subscriptions the engine dropped -----------------------------------------


async def test_bind_asks_the_engine_also_when_the_session_holds_it() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    # The engine drops the bind without a word, then the agent binds again.
    engine.engine_left([NAV], notify=False)
    result = await session.bind(NAV)
    assert result == {"component_ref": NAV, "bound": True}
    assert engine.holders[NAV] == {1}


async def test_an_engine_that_reconnects_drops_binds_and_subscriptions() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    subscribed = await session.subscribe(PEOPLE, "person_detected")
    engine.engine_left([NAV, PEOPLE])
    found = await session.events.wait_for(0, lambda entry: entry.kind == "lost", 1.0)
    assert found is not None
    assert found.data["binds"] == [NAV]
    assert [s["subscribe_id"] for s in found.data["subscriptions"]] == [subscribed["subscribe_id"]]
    state = session.state()
    assert state["binds"] == [] and state["subscriptions"] == []
    # A wait on the dead subscription ends at once with the loss.
    waited = await session.wait_for_event("person_detected", PEOPLE, timeout=1)
    assert waited["timed_out"] is False and waited["entry"]["kind"] == "lost"
    assert "Lost: robot/navigation" in waited["notice"]
    assert "Bind and subscribe again" in waited["notice"]
    listed = await session.list_components()
    assert listed["components"][0]["held_by_this_session"] is False


async def test_a_component_that_left_takes_its_subscriptions() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    await session.subscribe(PEOPLE, "person_detected")
    engine.hidden.add(PEOPLE)
    engine.engine_left([PEOPLE])
    found = await session.events.wait_for(0, lambda entry: entry.kind == "lost", 1.0)
    assert found is not None and found.data["binds"] == []
    assert session.state()["binds"] == [NAV]
    assert session.state()["subscriptions"] == []


async def test_a_profile_change_that_drops_nothing_says_nothing() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    engine.sessions[0].emit("rois.system.profile_changed", ProfileChangedParams())
    await asyncio.gather(*session._checks)
    assert session.state()["binds"] == [NAV]
    assert [entry["kind"] for entry in session.get_events()["entries"]] == ["profile_changed"]


async def test_a_dropped_bind_is_named_when_execute_fails() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    engine.engine_left([NAV], notify=False)
    with pytest.raises(AgentError) as caught:
        await session.run_commands([{"component_ref": NAV, "command_type": "start"}])
    assert "no longer holds this session's bind" in str(caught.value)
    assert "Not held any more: robot/navigation" in str(caught.value)
    assert session.state()["binds"] == []


async def test_auto_bind_renews_a_dropped_bind() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    engine.engine_left([NAV], notify=False)
    result = await session.run_commands(
        [{"component_ref": NAV, "command_type": "start"}], auto_bind=True
    )
    assert result["commands"][0]["status"] == "OK"
    assert "bound_by_this_call" not in result


async def test_set_parameters_on_a_dropped_bind_says_so() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    engine.engine_left([NAV], notify=False)
    with pytest.raises(AgentError, match="no longer holds this session's bind"):
        await session.set_parameters(NAV, {"target_positions": ["kitchen"]})
    assert session.state()["binds"] == []


# -- Hints --------------------------------------------------------------------------------


async def test_an_error_of_a_query_or_subscribe_is_not_about_binds() -> None:
    engine = Engine()
    engine.inoperable.add(NAV)
    session = make(engine)
    await session.bind(NAV)
    with pytest.raises(AgentError) as caught:
        await session.query(NAV, "available_targets")
    assert "cannot serve this now" in str(caught.value)
    assert "bind" not in str(caught.value)
    with pytest.raises(AgentError, match="cannot serve this now"):
        await session.subscribe(NAV, "reached_target")


def test_the_error_hint_depends_on_the_method_and_the_bind() -> None:
    def hint(method: str, held: bool = False) -> str:
        return str(rois_failure(RoISError(ReturnCode.ERROR, method), ref=NAV, held=held))

    assert "call bind first" in hint("rois.command.execute")
    assert "no longer holds this session's bind" in hint("rois.command.set_parameter", True)
    assert "cannot serve this now" in hint("rois.query.query", True)
    assert hint("rois.command.release").endswith("the engine refused the call")


async def test_a_refused_value_names_the_queries_that_list_valid_ones() -> None:
    engine = Engine()
    engine.refuse_values = True
    session = make(engine)
    await session.bind(NAV)
    with pytest.raises(AgentError) as caught:
        await session.set_parameters(NAV, {"target_positions": ["moon"]})
    assert "BAD_PARAMETER" in str(caught.value)
    assert "available_targets list the values it takes" in str(caught.value)


async def test_a_set_parameter_that_ends_error_names_the_queries_that_list_valid_ones() -> None:
    # Inside a sequence, the engine ends a refused set_parameter with ERROR, not with
    # BAD_PARAMETER, and the commands after it with ABORT.
    engine = Engine()
    engine.outcome["set_parameter"] = "ERROR"
    engine.outcome["start"] = "ABORT"
    session = make(engine)
    await session.bind(NAV)
    result = await session.run_commands(
        [
            {
                "component_ref": NAV,
                "command_type": "set_parameter",
                "arguments": {"target_positions": ["moon"]},
            },
            {"component_ref": NAV, "command_type": "start"},
        ]
    )
    refused, aborted = result["commands"]
    assert refused["status"] == "ERROR"
    assert "available_targets list the values it takes" in refused["hint"]
    assert "Tell the user rather than retrying" not in refused["hint"]
    assert f"because {refused['command_id']} on {NAV} ended ERROR" in aborted["hint"]
    # The same holds for set_parameters when the completion carries the ERROR.
    alone = await session.set_parameters(NAV, {"target_positions": ["moon"]})
    assert alone["status"] == "ERROR"
    assert "available_targets list the values it takes" in alone["hint"]


async def test_a_failed_command_comes_with_what_the_engine_reported() -> None:
    engine = Engine()
    engine.outcome["go"] = "ERROR"
    engine.outcome["stop"] = "ABORT"
    engine.error_on["go"] = "robot/err-7"
    session = make(engine)
    await session.bind(NAV)
    result = await session.run_commands(
        [
            {"component_ref": NAV, "command_type": "go", "arguments": {"speed": 1}},
            {"component_ref": NAV, "command_type": "stop"},
        ]
    )
    failed, aborted = result["commands"]
    assert failed["status"] == "ERROR"
    assert "RoIS carries no reason" in failed["hint"]
    assert failed["component_status"] == "READY"
    assert [error["error_id"] for error in failed["errors"]] == ["robot/err-7"]
    assert aborted["status"] == "ABORT"
    assert f"because {failed['command_id']} on {NAV} ended ERROR" in aborted["hint"]


async def test_subscribing_to_a_component_with_a_start_says_it_may_need_one() -> None:
    session = make(Engine())
    subscribed = await session.subscribe(NAV, "reached_target")
    assert "bind it and run_commands start" in subscribed["hint"]
    read_only = make(Engine(), allow_actions=False)
    subscribed = await read_only.subscribe(NAV, "reached_target")
    assert "--allow-actions" in subscribed["hint"]
    assert "hint" not in await session.subscribe(PEOPLE, "person_detected")


# -- Parameters in run_commands ----------------------------------------------------------


async def test_run_commands_sets_parameters_before_a_command() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    result = await session.run_commands(
        [
            {
                "component_ref": NAV,
                "command_type": "set_parameter",
                "arguments": {"target_positions": ["kitchen"]},
            },
            {"component_ref": NAV, "command_type": "start"},
        ]
    )
    assert [command["status"] for command in result["commands"]] == ["OK", "OK"]
    assert engine.executed[0][0] == {
        "component_ref": NAV,
        "command_type": "set_parameter",
        "arguments": [
            {"name": "target_positions", "data_type_ref": "string[]", "value": '["kitchen"]'}
        ],
    }
    with pytest.raises(AgentError, match="parameter model: read-only"):
        await session.run_commands(
            [{"component_ref": NAV, "command_type": "set_parameter", "arguments": {"model": "x"}}]
        )


async def test_a_parameter_given_as_an_argument_points_to_set_parameter() -> None:
    session = make(Engine())
    await session.bind(NAV)
    with pytest.raises(AgentError) as caught:
        await session.run_commands(
            [
                {
                    "component_ref": NAV,
                    "command_type": "start",
                    "arguments": {"target_positions": ["kitchen"]},
                }
            ]
        )
    assert "target_positions is a parameter of robot/navigation" in str(caught.value)
    assert '"command_type": "set_parameter"' in str(caught.value)


# -- Waiting for events --------------------------------------------------------------------


async def test_wait_for_event_sees_an_event_sent_during_the_command() -> None:
    engine = Engine()
    session = make(engine)
    subscribed = await session.subscribe(PEOPLE, "person_detected")
    ran = await session.run_commands(
        [{"component_ref": NAV, "command_type": "start"}], auto_bind=True, wait=False
    )
    # The count arrives before the agent calls wait_for_event.
    engine.sessions[0].fire(subscribed["subscribe_id"], 2)
    waited = await session.wait_for_event("person_detected", timeout=0.2)
    assert waited["timed_out"] is False
    assert waited["entry"]["results"][0]["value"] == 2
    assert waited["entry"]["seq"] > ran["cursor"]
    # The next wait starts after it, and a timeout keeps the cursor where it started.
    again = await session.wait_for_event("person_detected", timeout=0.05)
    assert again == {"timed_out": True, "cursor": waited["cursor"]}


async def test_the_subscribe_cursor_comes_before_the_subscription() -> None:
    engine = Engine()
    session = make(engine)
    session.events.append("completed", {})
    subscribed = await session.subscribe(PEOPLE, "person_detected")
    assert subscribed["cursor"] == 1
    engine.sessions[0].fire(subscribed["subscribe_id"], 1)
    assert (await session.wait_for_event(timeout=0.1))["timed_out"] is False


# -- A lost connection ---------------------------------------------------------------------


async def test_a_lost_connection_ends_a_wait_on_commands_at_once() -> None:
    engine = Engine()
    engine.outcome["start"] = None
    session = make(engine, command_timeout=5.0)
    await session.bind(NAV)

    async def drop_soon() -> None:
        await asyncio.sleep(0.05)
        engine.sessions[0].drop()

    task = asyncio.create_task(drop_soon())
    loop = asyncio.get_running_loop()
    began = loop.time()
    result = await session.run_commands([{"component_ref": NAV, "command_type": "start"}])
    await task
    assert loop.time() - began < 1.0
    assert result["commands"][0]["status"] == "CONNECTION_LOST"
    assert "aborted it with the session" in result["commands"][0]["hint"]
    assert "connection to the gateway was lost" in result["notice"]
    assert session.state()["running_commands"] == []


async def test_the_lost_session_notice_waits_for_a_response_that_carries_it() -> None:
    engine = Engine()
    session = make(engine)
    await session.bind(NAV)
    engine.sessions[0].drop()
    # The first call after the loss fails, so it cannot carry the notice.
    with pytest.raises(AgentError):
        await session.run_commands([{"component_ref": NAV, "command_type": "start"}])
    listed = await session.list_components()
    assert "connection to the gateway was lost" in listed["notice"]
