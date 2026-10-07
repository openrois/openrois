"""Tests for Component: the author side and the side the engine calls."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components import NAVIGATION_PROFILE, SYSTEM_INFORMATION_PROFILE
from openrois.interfaces.hri import Argument, Parameter, Result
from openrois.interfaces.profiles import HRIComponentProfile
from openrois.interfaces.service import CompletedStatus

from openrois.components.core import (
    CommandFailed,
    Component,
    component,
    invoke,
    on_set_parameter,
    query,
    subscribe,
)
from tests._support import RecordingBinding


@component(NAVIGATION_PROFILE)
class Navigation(Component):
    """A Navigation that drives nowhere, for the tests."""

    def __init__(self) -> None:
        self.applied: list[Mapping[str, Any]] = []
        self.subscribed = 0
        self.refuse = False
        self.arrive = asyncio.Event()

    @invoke("start")
    async def start(self) -> None:
        target = self.parameters["target_positions"][0]
        await self.arrive.wait()
        self.emit("reached_target", target=target, is_final_target=True)

    @invoke("suspend")
    async def suspend(self) -> None:
        raise CommandFailed(CompletedStatus.OUT_OF_RESOURCES, "brakes are hot")

    @invoke("resume")
    async def resume(self) -> None:
        raise RuntimeError("motor driver lost")

    @subscribe("reached_target")
    async def reached_target(self) -> None:
        self.subscribed += 1

    @on_set_parameter
    async def apply(self, values: Mapping[str, Any]) -> None:
        if self.refuse:
            raise ValueError("unknown place")
        self.applied.append(values)


@component(SYSTEM_INFORMATION_PROFILE)
class SystemInformation(Component):
    @query("robot_position")
    async def robot_position(self) -> dict[str, object]:
        return {
            "position_data": ["1.5,2.0,0.0"],
            "robot_ref": [self.ref.split("/")[0]],
            "timestamp": "2026-10-08T04:50:00+09:00",
        }

    @query("engine_status")
    async def engine_status(self) -> dict[str, object]:
        return {"status": ComponentStatus.READY}


def _bound_navigation() -> tuple[Navigation, RecordingBinding]:
    navigation = Navigation()
    binding = RecordingBinding.with_defaults(NAVIGATION_PROFILE)
    navigation.rois_bind(binding)
    return navigation, binding


def _set(binding: RecordingBinding, name: str, code: str, value: str) -> None:
    binding.stored = [p for p in binding.stored if p.name != name]
    binding.stored.append(Parameter(name=name, data_type_ref=code, value=value))


class TestParameters:
    def test_converted_from_their_profile_types(self) -> None:
        navigation, binding = _bound_navigation()
        _set(binding, "target_positions", "string[]", '["kitchen", "hall"]')
        assert navigation.parameters["target_positions"] == ["kitchen", "hall"]
        assert navigation.parameters["time_limit"] == 0
        assert navigation.parameters["routing_policy"] == "time"

    def test_a_parameter_without_a_value_is_missing(self) -> None:
        navigation, _ = _bound_navigation()
        assert "target_positions" not in navigation.parameters

    def test_read_only(self) -> None:
        navigation, _ = _bound_navigation()
        with pytest.raises(TypeError):
            navigation.parameters["time_limit"] = 5  # type: ignore[index]

    def test_need_an_engine(self) -> None:
        with pytest.raises(RuntimeError, match="No engine"):
            Navigation().parameters


class TestCommands:
    async def test_runs_for_as_long_as_the_command_lasts(self) -> None:
        navigation, binding = _bound_navigation()
        _set(binding, "target_positions", "string[]", '["kitchen"]')
        running = asyncio.create_task(navigation.rois_command("start"))
        await asyncio.sleep(0)
        assert not running.done()
        navigation.arrive.set()
        assert await running == []
        assert binding.events == [
            (
                "reached_target",
                [
                    Result(name="target", data_type_ref="string", value="kitchen"),
                    Result(name="is_final_target", data_type_ref="bool", value="true"),
                ],
            )
        ]

    async def test_command_failed_carries_its_status(self) -> None:
        navigation, _ = _bound_navigation()
        with pytest.raises(CommandFailed) as failure:
            await navigation.rois_command("suspend")
        assert failure.value.status is CompletedStatus.OUT_OF_RESOURCES

    async def test_other_exceptions_propagate(self) -> None:
        navigation, _ = _bound_navigation()
        with pytest.raises(RuntimeError, match="motor driver"):
            await navigation.rois_command("resume")

    async def test_stop_without_a_handler_returns_at_once(self) -> None:
        navigation, _ = _bound_navigation()
        assert await navigation.rois_command("stop") == []

    async def test_a_command_the_class_does_not_serve(self) -> None:
        @component(NAVIGATION_PROFILE)
        class StartOnly(Component):
            @invoke("start")
            async def start(self) -> None:
                return None

        with pytest.raises(ValueError, match="'suspend'"):
            await StartOnly().rois_command("suspend")

    def test_command_failed_never_ends_ok(self) -> None:
        with pytest.raises(ValueError):
            CommandFailed(CompletedStatus.OK)


class TestArgumentsAndResults:
    PROFILE = HRIComponentProfile.model_validate(
        {
            "identifier": {"authority": "Example", "code": "Speech"},
            "name": "speech",
            "command_profiles": [
                {
                    "name": "say",
                    "arguments": [
                        {"name": "text", "data_type_ref": {"code": "string"}},
                        {"name": "volume", "data_type_ref": {"code": "int"}},
                    ],
                    "results": [{"name": "spoken_ms", "data_type_ref": {"code": "int"}}],
                }
            ],
        }
    )

    def _speech(self) -> Component:
        @component(self.PROFILE)
        class Speech(Component):
            @invoke("say")
            async def say(self, text: str, volume: int = 5) -> dict[str, object]:
                return {"spoken_ms": len(text) * 100 + volume}

        return Speech()

    async def test_arguments_arrive_by_name_and_type(self) -> None:
        results = await self._speech().rois_command(
            "say",
            [
                Argument(name="text", data_type_ref="string", value="hi"),
                Argument(name="volume", data_type_ref="int", value="3"),
            ],
        )
        assert results == [Result(name="spoken_ms", data_type_ref="int", value="203")]

    async def test_an_unknown_argument(self) -> None:
        with pytest.raises(ValueError, match="no argument 'speed'"):
            await self._speech().rois_command(
                "say", [Argument(name="speed", data_type_ref="int", value="1")]
            )

    async def test_an_argument_that_does_not_fit_its_type(self) -> None:
        with pytest.raises(ValueError):
            await self._speech().rois_command(
                "say", [Argument(name="volume", data_type_ref="int", value="loud")]
            )


class TestQueries:
    async def test_results_follow_the_profile(self) -> None:
        info = SystemInformation()
        info.rois_bind(RecordingBinding(ref="robot_1/system_information"))
        assert await info.rois_query("robot_position") == [
            Result(name="position_data", data_type_ref="String[]", value='["1.5,2.0,0.0"]'),
            Result(name="robot_ref", data_type_ref="RoISIdentifier[]", value='["robot_1"]'),
            Result(name="timestamp", data_type_ref="DateTime", value="2026-10-08T04:50:00+09:00"),
        ]

    async def test_status_travels_as_its_name(self) -> None:
        results = await SystemInformation().rois_query("engine_status")
        assert results == [Result(name="status", data_type_ref="Component_Status", value="READY")]

    async def test_component_status_is_not_the_component_s(self) -> None:
        navigation, _ = _bound_navigation()
        with pytest.raises(ValueError, match="does not answer"):
            await navigation.rois_query("component_status")

    async def test_unknown_result_names(self) -> None:
        @component(SYSTEM_INFORMATION_PROFILE)
        class Wrong(Component):
            @query("engine_status")
            async def engine_status(self) -> dict[str, object]:
                return {"state": "READY"}

        with pytest.raises(ValueError, match="no result named state"):
            await Wrong().rois_query("engine_status")

    async def test_results_are_a_mapping(self) -> None:
        @component(SYSTEM_INFORMATION_PROFILE)
        class Listed(Component):
            @query("engine_status")
            async def engine_status(self) -> list[Result]:
                return []

        with pytest.raises(TypeError, match="by name"):
            await Listed().rois_query("engine_status")


class TestEvents:
    async def test_subscribe_method_runs_on_each_subscription(self) -> None:
        navigation, _ = _bound_navigation()
        await navigation.rois_subscribed("reached_target")
        await navigation.rois_subscribed("reached_target")
        assert navigation.subscribed == 2

    def test_emit_leaves_out_what_it_is_not_given(self) -> None:
        navigation, binding = _bound_navigation()
        navigation.emit("reached_target", target="hall")
        assert binding.events == [
            ("reached_target", [Result(name="target", data_type_ref="string", value="hall")])
        ]

    def test_emit_an_event_the_class_does_not_serve(self) -> None:
        @component(NAVIGATION_PROFILE)
        class Silent(Component):
            pass

        silent = Silent()
        silent.rois_bind(RecordingBinding())
        with pytest.raises(ValueError, match="@subscribe"):
            silent.emit("reached_target", target="hall")

    def test_emit_checks_value_types(self) -> None:
        navigation, _ = _bound_navigation()
        with pytest.raises(ValueError):
            navigation.emit("reached_target", is_final_target="yes")

    def test_emit_needs_an_engine(self) -> None:
        with pytest.raises(RuntimeError, match="No engine"):
            Navigation().emit("reached_target", target="hall")


class TestSetParameterHook:
    async def test_receives_the_new_values_converted(self) -> None:
        navigation, _ = _bound_navigation()
        await navigation.rois_set_parameters(
            [
                Parameter(name="target_positions", data_type_ref="string[]", value='["dock"]'),
                Parameter(name="time_limit", data_type_ref="int", value="30"),
            ]
        )
        assert navigation.applied == [{"target_positions": ["dock"], "time_limit": 30}]

    async def test_refuses_by_raising(self) -> None:
        navigation, _ = _bound_navigation()
        navigation.refuse = True
        with pytest.raises(ValueError, match="unknown place"):
            await navigation.rois_set_parameters(
                [Parameter(name="target_positions", data_type_ref="string[]", value='["moon"]')]
            )

    async def test_a_parameter_the_profile_lacks(self) -> None:
        navigation, _ = _bound_navigation()
        with pytest.raises(ValueError, match="'speed'"):
            await navigation.rois_set_parameters(
                [Parameter(name="speed", data_type_ref="float", value="1.0")]
            )

    async def test_without_a_hook_nothing_runs(self) -> None:
        await SystemInformation().rois_set_parameters([])


async def test_connect_and_disconnect_default_to_nothing() -> None:
    info = SystemInformation()
    await info.connect()
    await info.disconnect()
