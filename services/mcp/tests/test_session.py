"""Tests of the session against a fake engine with binds."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from openrois.interfaces import ReturnCode

from openrois.mcp.config import Settings
from openrois.mcp.session import AgentError, Session
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
    entries = session.get_events()["entries"]
    assert entries[-1]["kind"] == "connection_closed"
    listed = await session.list_components()
    assert "binds, subscriptions and running commands" in listed["notice"]
    assert session.state()["binds"] == []
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
