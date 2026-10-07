"""Tests for @component: the handlers it collects and the profile it serves."""

from __future__ import annotations

from typing import Any

import pytest
from openrois.interfaces.components import (
    NAVIGATION_PROFILE,
    PERSON_DETECTION_PROFILE,
    SYSTEM_INFORMATION_PROFILE,
)
from openrois.interfaces.profiles import HRIComponentProfile, RoISIdentifierType

from openrois.components.core import (
    Component,
    component,
    invoke,
    on_set_parameter,
    query,
    subscribe,
)


def _names(messages: list[Any]) -> list[str]:
    return [m.name for m in messages]


@component(NAVIGATION_PROFILE)
class StartOnly(Component):
    """A Navigation that implements start and nothing else."""

    @invoke("start")
    async def start(self) -> None:
        return None


class TestServedProfile:
    def test_serves_only_what_the_class_implements(self) -> None:
        served = StartOnly.rois_profile()
        assert _names(served.command_profiles) == ["start", "stop"]
        assert _names(served.query_profiles) == ["component_status"]
        assert served.event_profiles == []

    def test_keeps_the_identity_and_the_parameters(self) -> None:
        served = StartOnly.rois_profile()
        assert served.identifier == NAVIGATION_PROFILE.identifier
        assert served.function == NAVIGATION_PROFILE.function
        assert served.sub_component_profiles == NAVIGATION_PROFILE.sub_component_profiles
        assert served.parameter_profiles == NAVIGATION_PROFILE.parameter_profiles

    def test_serves_stop_only_with_start(self) -> None:
        @component(PERSON_DETECTION_PROFILE)
        class Suspendable(Component):
            @invoke("suspend")
            async def suspend(self) -> None:
                return None

        assert _names(Suspendable.rois_profile().command_profiles) == ["suspend"]

    def test_serves_an_event_marked_with_subscribe(self) -> None:
        @component(PERSON_DETECTION_PROFILE)
        class Detector(Component):
            @subscribe("person_detected")
            async def person_detected(self) -> None:
                return None

        assert _names(Detector.rois_profile().event_profiles) == ["person_detected"]

    def test_component_status_only_where_the_profile_has_it(self) -> None:
        @component(SYSTEM_INFORMATION_PROFILE)
        class Info(Component):
            @query("engine_status")
            async def engine_status(self) -> dict[str, object]:
                return {}

        assert _names(Info.rois_profile().query_profiles) == ["engine_status"]

    def test_the_declared_constant_is_not_changed(self) -> None:
        assert _names(NAVIGATION_PROFILE.command_profiles) == ["start", "stop", "suspend", "resume"]

    def test_a_subclass_keeps_the_declaration(self) -> None:
        class Faster(StartOnly):
            pass

        assert Faster.rois_profile() == StartOnly.rois_profile()


class TestDeclarationErrors:
    def test_profile_must_be_a_profile(self) -> None:
        with pytest.raises(TypeError, match="HRIComponentProfile"):
            component("Navigation")  # type: ignore[arg-type]

    def test_class_must_subclass_component(self) -> None:
        with pytest.raises(TypeError, match="subclass of Component"):

            @component(NAVIGATION_PROFILE)
            class Plain:  # type: ignore[type-var]
                pass

    def test_command_the_profile_lacks(self) -> None:
        with pytest.raises(ValueError, match="'jump'"):

            @component(NAVIGATION_PROFILE)
            class Jumper(Component):
                @invoke("jump")
                async def jump(self) -> None:
                    return None

    def test_query_the_profile_lacks(self) -> None:
        with pytest.raises(ValueError, match="'battery'"):

            @component(NAVIGATION_PROFILE)
            class Battery(Component):
                @query("battery")
                async def battery(self) -> dict[str, object]:
                    return {}

    def test_event_the_profile_lacks(self) -> None:
        with pytest.raises(ValueError, match="'arrived'"):

            @component(NAVIGATION_PROFILE)
            class Arrival(Component):
                @subscribe("arrived")
                async def arrived(self) -> None:
                    return None

    def test_set_parameter_is_not_a_command(self) -> None:
        with pytest.raises(ValueError, match="on_set_parameter"):

            @component(NAVIGATION_PROFILE)
            class Setter(Component):
                @invoke("set_parameter")
                async def set_parameter(self) -> None:
                    return None

    def test_component_status_is_answered_by_the_engine(self) -> None:
        with pytest.raises(ValueError, match="engine answers"):

            @component(NAVIGATION_PROFILE)
            class Status(Component):
                @query("component_status")
                async def status(self) -> dict[str, object]:
                    return {}

    def test_two_handlers_for_one_command(self) -> None:
        with pytest.raises(ValueError, match="both handle"):

            @component(NAVIGATION_PROFILE)
            class Twice(Component):
                @invoke("start")
                async def first(self) -> None:
                    return None

                @invoke("start")
                async def second(self) -> None:
                    return None

    def test_one_method_one_message(self) -> None:
        with pytest.raises(ValueError, match="already handles"):

            class Double(Component):
                @invoke("start")
                @invoke("stop")
                async def both(self) -> None:
                    return None

    def test_handlers_are_coroutines(self) -> None:
        with pytest.raises(TypeError, match="async def"):

            @component(NAVIGATION_PROFILE)
            class Sync(Component):
                @invoke("start")
                def start(self) -> None:
                    return None

    def test_command_parameters_are_its_arguments(self) -> None:
        with pytest.raises(TypeError, match="'target'"):

            @component(NAVIGATION_PROFILE)
            class Targeted(Component):
                @invoke("start")
                async def start(self, target: str) -> None:
                    return None

    def test_queries_take_no_arguments(self) -> None:
        with pytest.raises(TypeError, match="no arguments"):

            @component(SYSTEM_INFORMATION_PROFILE)
            class Positioned(Component):
                @query("robot_position")
                async def robot_position(self, precise: bool) -> dict[str, object]:
                    return {}

    def test_hook_needs_parameters_in_the_profile(self) -> None:
        with pytest.raises(ValueError, match="declares no parameters"):

            @component(PERSON_DETECTION_PROFILE)
            class Hooked(Component):
                @on_set_parameter
                async def apply(self, values: dict[str, object]) -> None:
                    return None

    def test_one_hook(self) -> None:
        with pytest.raises(ValueError, match="two @on_set_parameter"):

            @component(NAVIGATION_PROFILE)
            class TwoHooks(Component):
                @on_set_parameter
                async def first(self, values: dict[str, object]) -> None:
                    return None

                @on_set_parameter
                async def second(self, values: dict[str, object]) -> None:
                    return None

    def test_hook_takes_the_values(self) -> None:
        with pytest.raises(TypeError, match="one argument"):

            @component(NAVIGATION_PROFILE)
            class NoValues(Component):
                @on_set_parameter
                async def apply(self) -> None:
                    return None

    def test_undeclared_class_has_no_profile(self) -> None:
        class Undeclared(Component):
            pass

        with pytest.raises(TypeError, match="not declared"):
            Undeclared.rois_profile()


def test_user_defined_profile() -> None:
    """A component outside the basic set declares a full profile of its own."""
    profile = HRIComponentProfile.model_validate(
        {
            "identifier": RoISIdentifierType(authority="Example", code="Speech"),
            "name": "speech",
            "function": "actuation",
            "command_profiles": [
                {
                    "name": "say",
                    "arguments": [{"name": "text", "data_type_ref": {"code": "string"}}],
                }
            ],
        }
    )

    @component(profile)
    class Speech(Component):
        @invoke("say")
        async def say(self, text: str) -> None:
            return None

    assert _names(Speech.rois_profile().command_profiles) == ["say"]
