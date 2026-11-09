"""Tests for openrois.interfaces.declaration, user-defined components (stream I, step 6).

The two components of Annex C: the wheelchair (C.4) and the speech recognizer (C.1).
An integrator declares a component in Python, the declaration builds the profile, and
the XML codec writes it.
"""

from __future__ import annotations

from typing import Any

import pytest
from openrois.interfaces.declaration import (
    Command,
    ComponentDeclaration,
    DeclarationError,
    Event,
    Param,
    Query,
)

from openrois.interfaces.components import ROIS_COMMON_PROFILE, ROIS_COMMON_URN
from openrois.interfaces.components.standard_profiles import standard_registry
from openrois.interfaces.profiles import ComponentFunction, RoISIdentifierType
from openrois.interfaces.type_codes import python_type
from openrois.interfaces.xmlcodec import (
    read_component_profile,
    write_component_profile,
)

WHEELCHAIR_STATUS = (
    Param("position", "String", "robot position in comma separated double values [x.x, y.y]"),
    Param("brake_status", "Boolean", "wheelchair brake status"),
    Param("pause_status", "Boolean", "wheelchair pause status"),
    Param("wc_status", "String", "running, obstacle, path_error, stopped, brakes or paused"),
    Param("nav_status", "String", "running or stopped"),
)

WHEELCHAIR = ComponentDeclaration(
    identifier="urn:x-rois:def:component:ACME::Wheelchair",
    name="wheelchair",
    function="actuation",
    commands=[Command("brake", arguments=[Param("status", "Boolean", "brake status")])],
    queries=[Query("wc_status_change", results=WHEELCHAIR_STATUS)],
    events=[Event("wc_status_change", results=WHEELCHAIR_STATUS)],
    parameters=[
        Param("preferred_max_speed", "Double", "preferred max speed in mm/s"),
        Param("behaviour_tag", "String", "tag of the interaction scenario"),
        Param("navigation_mode", "String", "Location or Tag", default="Location"),
    ],
)

SPEECH_RECOGNIZER = ComponentDeclaration(
    identifier="urn:x-rois:def:component:ACME::SrgsSpeechRecognition",
    name="srgs_speech_recognizer",
    function=ComponentFunction.SENSING,
    events=[
        Event(
            "speech_recognized",
            results=[
                Param("timestamp", "DateTime"),
                Param("timestamp_speech_start", "DateTime"),
                Param("timestamp_speech_end", "DateTime"),
                Param("nbest", "NbestType"),
                Param("lattice", "LatticeType"),
                Param("position_of_sound", "Data"),
            ],
        ),
        Event("speech_input_started"),
        Event("speech_input_finished"),
        Event("speech_recognition_started"),
        Event("speech_recognition_finished"),
    ],
    parameters=[
        Param("languages", "Set<String>"),
        Param("position_of_sound", "Data"),
        Param("grammar", "String"),
        Param("active_rule", "RuleReference"),
        Param("recognizable_languages", "Set<String>", read_only=True),
    ],
)


class TestWheelchair:
    def test_identity(self) -> None:
        profile = WHEELCHAIR.profile()
        assert profile.identifier == RoISIdentifierType(authority="ACME", code="Wheelchair")
        assert profile.name == "wheelchair"
        assert profile.function is ComponentFunction.ACTUATION

    def test_includes_rois_common_by_default(self) -> None:
        profile = WHEELCHAIR.profile()
        assert profile.sub_component_profiles == [ROIS_COMMON_URN]
        assert [c.name for c in profile.command_profiles] == [
            "start",
            "stop",
            "suspend",
            "resume",
            "brake",
        ]
        assert profile.query_profiles[0] == ROIS_COMMON_PROFILE.query_profiles[0]

    def test_brake_takes_a_boolean(self) -> None:
        brake = WHEELCHAIR.profile().command_profiles[-1]
        assert [(a.name, a.data_type_ref.code) for a in brake.arguments] == [
            ("status", "Boolean")
        ]
        assert python_type("Boolean") is Any

    def test_query_and_event_share_a_name(self) -> None:
        profile = WHEELCHAIR.profile()
        query = profile.query_profiles[-1]
        event = profile.event_profiles[-1]
        assert query.name == event.name == "wc_status_change"
        assert query.results == event.results

    def test_parameters(self) -> None:
        params = {p.name: p for p in WHEELCHAIR.profile().parameter_profiles}
        assert params["preferred_max_speed"].data_type_ref.code == "Double"
        assert params["preferred_max_speed"].default_value is None
        assert params["navigation_mode"].default_value == "Location"

    def test_writes_xml(self) -> None:
        registry = standard_registry()
        profile = WHEELCHAIR.profile()
        xml = WHEELCHAIR.to_xml()
        assert xml == write_component_profile(profile, registry=registry)
        assert b'rois:name="start"' not in xml
        read = read_component_profile(xml, registry=registry)
        assert read == profile.model_copy(update={"function": None})


class TestSpeechRecognizer:
    def test_foreign_type_codes_are_kept(self) -> None:
        profile = SPEECH_RECOGNIZER.profile()
        codes = {p.name: p.data_type_ref.code for p in profile.parameter_profiles}
        assert codes["languages"] == "Set<String>"
        assert codes["active_rule"] == "RuleReference"
        nbest = profile.event_profiles[0].results[3]
        assert nbest.data_type_ref.code == "NbestType"
        assert python_type("Set<String>") is Any

    def test_read_only_parameter(self) -> None:
        params = {p.name: p for p in SPEECH_RECOGNIZER.profile().parameter_profiles}
        assert params["recognizable_languages"].read_only is True
        assert params["languages"].read_only is False

    def test_events_without_results(self) -> None:
        names = [e.name for e in SPEECH_RECOGNIZER.profile().event_profiles]
        assert names == [
            "speech_recognized",
            "speech_input_started",
            "speech_input_finished",
            "speech_recognition_started",
            "speech_recognition_finished",
        ]

    def test_round_trip_through_xml(self) -> None:
        registry = standard_registry()
        profile = SPEECH_RECOGNIZER.profile()
        read = read_component_profile(SPEECH_RECOGNIZER.to_xml(), registry=registry)
        unmarked = [p.model_copy(update={"read_only": False}) for p in profile.parameter_profiles]
        assert read == profile.model_copy(
            update={"function": None, "parameter_profiles": unmarked}
        )


class TestDeclarationRules:
    def test_without_sub_profiles(self) -> None:
        bare = ComponentDeclaration(
            identifier="urn:x-rois:def:component:ACME::Lamp",
            name="lamp",
            function="actuation",
            commands=[Command("switch", arguments=[Param("on", "bool")], timeout=200)],
            sub_profiles=(),
        )
        profile = bare.profile()
        assert profile.sub_component_profiles == []
        assert [c.name for c in profile.command_profiles] == ["switch"]
        assert profile.command_profiles[0].timeout == 200

    @pytest.mark.parametrize(
        "function", [ComponentFunction.SENSING, "sensing", "actuation", "function"]
    )
    def test_function_kinds(self, function: ComponentFunction | str) -> None:
        declaration = ComponentDeclaration(
            identifier="urn:x-rois:def:component:ACME::Thing", name="thing", function=function
        )
        assert declaration.profile().function == ComponentFunction(function)

    def test_unknown_function_is_refused(self) -> None:
        with pytest.raises(DeclarationError):
            ComponentDeclaration(
                identifier="urn:x-rois:def:component:ACME::Thing", name="thing", function="other"
            )

    def test_duplicate_name_within_a_kind_is_refused(self) -> None:
        with pytest.raises(DeclarationError):
            ComponentDeclaration(
                identifier="urn:x-rois:def:component:ACME::Thing",
                name="thing",
                function="sensing",
                queries=[Query("status"), Query("status")],
            )

    def test_redeclaring_an_inherited_message_is_refused(self) -> None:
        declaration = ComponentDeclaration(
            identifier="urn:x-rois:def:component:ACME::Thing",
            name="thing",
            function="actuation",
            commands=[Command("start")],
        )
        with pytest.raises(DeclarationError):
            declaration.profile()

    def test_duplicate_parameter_is_refused(self) -> None:
        with pytest.raises(DeclarationError):
            ComponentDeclaration(
                identifier="urn:x-rois:def:component:ACME::Thing",
                name="thing",
                function="sensing",
                parameters=[Param("p", "int"), Param("p", "int")],
            )

    def test_duplicate_argument_is_refused(self) -> None:
        with pytest.raises(DeclarationError):
            Command("go", arguments=[Param("x", "int"), Param("x", "int")])

    def test_typed_default_is_written_as_its_string_form(self) -> None:
        declaration = ComponentDeclaration(
            identifier="urn:x-rois:def:component:ACME::Thing",
            name="thing",
            function="sensing",
            parameters=[
                Param("limit", "int", default=10),
                Param("enabled", "bool", default=True),
                Param("tags", "string[]", default=["a", "b"]),
            ],
        )
        defaults = [p.default_value for p in declaration.profile().parameter_profiles]
        assert defaults == ["10", "true", '["a", "b"]']
