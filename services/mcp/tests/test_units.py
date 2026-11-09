"""Tests of the pure parts: settings, the allow filter, profiles, values and the buffer."""

from __future__ import annotations

import asyncio

import pytest
from openrois.interfaces import Parameter, Result

from openrois.mcp import profiles, values
from openrois.mcp.allow import AllowFilter
from openrois.mcp.config import ConfigError, build_parser, load_settings
from openrois.mcp.events import EventBuffer
from tests.fakes import NAVIGATION, PEOPLE

# -- Settings -----------------------------------------------------------------


def test_defaults_are_read_only_on_loopback() -> None:
    settings = load_settings(build_parser().parse_args([]), environ={})
    assert settings.gateway_url == "ws://127.0.0.1:8765"
    assert settings.allow_actions is False
    assert settings.allow == ()
    assert settings.idle_release is None
    assert settings.transport == "stdio"


def test_flags_override_the_environment() -> None:
    env = {
        "OPENROIS_MCP_GATEWAY_URL": "ws://env:1",
        "OPENROIS_MCP_ALLOW_ACTIONS": "true",
        "OPENROIS_MCP_ALLOW": "a/%, b/%",
        "OPENROIS_MCP_COMMAND_TIMEOUT": "5",
    }
    settings = load_settings(
        build_parser().parse_args(["--gateway-url", "ws://flag:2", "--allow", "c/%"]),
        environ=env,
    )
    assert settings.gateway_url == "ws://flag:2"
    assert settings.allow_actions is True
    assert settings.allow == ("c/%",)
    assert settings.command_timeout == 5.0


def test_environment_patterns_are_split() -> None:
    env = {"OPENROIS_MCP_ALLOW": "a/%,b/x"}
    settings = load_settings(build_parser().parse_args([]), environ=env)
    assert settings.allow == ("a/%", "b/x")


def test_idle_release_is_off_unless_set() -> None:
    parser = build_parser()
    off = load_settings(parser.parse_args(["--idle-release", "0"]), environ={})
    on = load_settings(parser.parse_args(["--idle-release", "300"]), environ={})
    assert off.idle_release is None
    assert on.idle_release == 300


@pytest.mark.parametrize("flag", ["--command-timeout", "--event-buffer"])
def test_bad_numbers_are_refused(flag: str) -> None:
    with pytest.raises(ConfigError):
        load_settings(build_parser().parse_args([flag, "-1"]), environ={})


# -- Allow filter -------------------------------------------------------------


def test_no_pattern_allows_every_component() -> None:
    assert AllowFilter().allows("anything/at_all")


def test_like_patterns() -> None:
    allow = AllowFilter(["reachy_real/%", "mock/nav_gation"])
    assert allow.allows("reachy_real/head")
    assert allow.allows("mock/navigation")
    assert not allow.allows("reachy_sim/head")
    assert not allow.allows("xreachy_real/head")


def test_escaped_wildcards_are_literal() -> None:
    allow = AllowFilter(["a/100\\%"])
    assert allow.allows("a/100%")
    assert not allow.allows("a/1000")


# -- Profiles -----------------------------------------------------------------


def test_summary_names_what_a_component_offers() -> None:
    summary = profiles.summary("robot/navigation", NAVIGATION)
    assert summary == {
        "ref": "robot/navigation",
        "type": "OMG::Navigation",
        "engine": "robot",
        "function": "actuation",
        "commands": ["start", "stop", "go"],
        "queries": ["component_status", "available_targets"],
        "events": ["reached_target"],
    }


def test_describe_types_every_field() -> None:
    described = profiles.describe("robot/navigation", NAVIGATION)
    assert described["needs_exclusive_bind"] is True
    go = next(command for command in described["commands"] if command["name"] == "go")
    assert go["arguments"] == [{"name": "speed", "type": "double"}]
    assert {"name": "model", "type": "string", "read_only": True} in described["parameters"]
    assert profiles.describe("robot/person_detection", PEOPLE)["needs_exclusive_bind"] is False


def test_parameters_show_their_initial_value_as_json() -> None:
    described = profiles.describe("robot/navigation", NAVIGATION)
    target = next(p for p in described["parameters"] if p["name"] == "target_positions")
    assert target == {"name": "target_positions", "type": "string[]", "initial_value": []}
    assert "stay on the component between sessions" in described["parameters_note"]


def test_engine_of_nested_refs() -> None:
    assert profiles.engine_of("gateway/reachy/head") == "gateway/reachy"


# -- Values -------------------------------------------------------------------


def test_encode_types_plain_values_by_the_profile() -> None:
    items = values.encode(
        {"target_positions": ["kitchen", "hall"], "time_limit": 30},
        NAVIGATION.parameter_profiles,
    )
    assert items == [
        {"name": "target_positions", "data_type_ref": "string[]", "value": '["kitchen", "hall"]'},
        {"name": "time_limit", "data_type_ref": "int", "value": "30"},
    ]


def test_encode_names_the_refused_parameter() -> None:
    with pytest.raises(values.ValueRefusedError) as caught:
        values.encode({"time_limit": "soon"}, NAVIGATION.parameter_profiles)
    assert caught.value.name == "time_limit"
    with pytest.raises(values.ValueRefusedError, match="not declared"):
        values.encode({"colour": "red"}, NAVIGATION.parameter_profiles)
    with pytest.raises(values.ValueRefusedError, match="read-only"):
        values.encode({"model": "x"}, NAVIGATION.parameter_profiles, refuse_read_only=True)


def test_decode_gives_json_values() -> None:
    decoded = values.decode(
        [
            Result(name="number", data_type_ref="int", value="3"),
            Result(name="status", data_type_ref="Component_Status", value="READY"),
            Parameter(name="names", data_type_ref="string[]", value='["a"]'),
            Result(name="broken", data_type_ref="int", value="three"),
        ]
    )
    assert [item["value"] for item in decoded] == [3, "READY", ["a"], "three"]


# -- Event buffer -------------------------------------------------------------


async def test_cursor_reads_each_entry_once() -> None:
    buffer = EventBuffer(10)
    for number in range(3):
        buffer.append("event", {"n": number})
    first, cursor, dropped = buffer.since(0, 2)
    assert [entry.data["n"] for entry in first] == [0, 1]
    rest, cursor, dropped = buffer.since(cursor, 10)
    assert [entry.data["n"] for entry in rest] == [2]
    assert buffer.since(cursor, 10)[0] == []
    assert dropped == 0


async def test_a_full_buffer_reports_what_it_dropped() -> None:
    buffer = EventBuffer(2)
    for number in range(5):
        buffer.append("event", {"n": number})
    entries, cursor, dropped = buffer.since(0, 10)
    assert [entry.data["n"] for entry in entries] == [3, 4]
    assert dropped == 3
    assert cursor == 5


async def test_wait_for_returns_the_first_match_after_the_cursor() -> None:
    buffer = EventBuffer(10)
    buffer.append("event", {"n": 0})

    async def later() -> None:
        await asyncio.sleep(0.01)
        buffer.append("event", {"n": 1})
        buffer.append("event", {"n": 2})

    task = asyncio.create_task(later())
    found = await buffer.wait_for(buffer.last, lambda entry: entry.data["n"] == 2, 1.0)
    await task
    assert found is not None and found.data["n"] == 2


async def test_wait_for_times_out() -> None:
    buffer = EventBuffer(10)
    assert await buffer.wait_for(0, lambda entry: True, 0.01) is None
