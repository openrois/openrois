"""Tests for the profile constants of the basic components.

These tests run without the normative files. test_xml_crosscheck.py compares every
constant with the XML profiles when OPENROIS_NORMATIVE_DIR is set.
"""

from __future__ import annotations

import pytest

from openrois.interfaces.components import (
    NAVIGATION_PROFILE,
    NAVIGATION_URN,
    PERSON_DETECTION_PROFILE,
    PERSON_DETECTION_URN,
    REACTION_PROFILE,
    REACTION_URN,
    ROIS_COMMON_PROFILE,
    ROIS_COMMON_URN,
    SPEECH_SYNTHESIS_PROFILE,
    SPEECH_SYNTHESIS_URN,
    SYSTEM_INFORMATION_PROFILE,
    SYSTEM_INFORMATION_URN,
    profiles_document,
)
from openrois.interfaces.condition import component_type_urn
from openrois.interfaces.profiles import ComponentFunction, HRIComponentProfile

INCLUDING_ROIS_COMMON = [
    NAVIGATION_PROFILE,
    PERSON_DETECTION_PROFILE,
    REACTION_PROFILE,
    SPEECH_SYNTHESIS_PROFILE,
]
ALL_PROFILES = [ROIS_COMMON_PROFILE, *INCLUDING_ROIS_COMMON, SYSTEM_INFORMATION_PROFILE]


def _names(messages: list) -> list[str]:  # type: ignore[type-arg]
    return [m.name for m in messages]


@pytest.mark.parametrize("profile", ALL_PROFILES, ids=lambda p: p.identifier.code)
def test_profile_round_trips(profile: HRIComponentProfile) -> None:
    """Each constant survives a dump to JSON and back."""
    assert HRIComponentProfile.model_validate_json(profile.model_dump_json()) == profile


@pytest.mark.parametrize(
    ("profile", "urn"),
    [
        (NAVIGATION_PROFILE, NAVIGATION_URN),
        (PERSON_DETECTION_PROFILE, PERSON_DETECTION_URN),
        (REACTION_PROFILE, REACTION_URN),
        (SPEECH_SYNTHESIS_PROFILE, SPEECH_SYNTHESIS_URN),
        (SYSTEM_INFORMATION_PROFILE, SYSTEM_INFORMATION_URN),
    ],
    ids=lambda value: value if isinstance(value, str) else value.identifier.code,
)
def test_identifier_matches_urn(profile: HRIComponentProfile, urn: str) -> None:
    """The identifier of each component profile spells the URN of its module."""
    assert component_type_urn(profile.identifier) == urn


def test_rois_common_profile() -> None:
    """RoIS_Common has the four commands and the component_status query."""
    assert ROIS_COMMON_URN.endswith("::RoISCommon")
    assert _names(ROIS_COMMON_PROFILE.command_profiles) == ["start", "stop", "suspend", "resume"]
    assert _names(ROIS_COMMON_PROFILE.query_profiles) == ["component_status"]
    status = ROIS_COMMON_PROFILE.query_profiles[0].results[0]
    assert status.name == "status"
    assert status.data_type_ref.code == "Component_Status"


@pytest.mark.parametrize("profile", INCLUDING_ROIS_COMMON, ids=lambda p: p.identifier.code)
def test_rois_common_messages_come_first(profile: HRIComponentProfile) -> None:
    """A profile that includes RoIS_Common lists its messages before its own."""
    assert profile.sub_component_profiles == [ROIS_COMMON_URN]
    common_commands = ROIS_COMMON_PROFILE.command_profiles
    common_queries = ROIS_COMMON_PROFILE.query_profiles
    assert profile.command_profiles[: len(common_commands)] == common_commands
    assert profile.query_profiles[: len(common_queries)] == common_queries


def test_system_information_has_no_rois_common() -> None:
    """SystemInformation.xml includes no RoIS_Common: two queries and nothing else."""
    assert SYSTEM_INFORMATION_PROFILE.sub_component_profiles == []
    assert SYSTEM_INFORMATION_PROFILE.command_profiles == []
    assert _names(SYSTEM_INFORMATION_PROFILE.query_profiles) == ["robot_position", "engine_status"]


@pytest.mark.parametrize(
    ("profile", "function"),
    [
        (ROIS_COMMON_PROFILE, None),
        (NAVIGATION_PROFILE, ComponentFunction.ACTUATION),
        (PERSON_DETECTION_PROFILE, ComponentFunction.SENSING),
        (REACTION_PROFILE, ComponentFunction.ACTUATION),
        (SPEECH_SYNTHESIS_PROFILE, ComponentFunction.ACTUATION),
        (SYSTEM_INFORMATION_PROFILE, None),
    ],
    ids=lambda v: v.identifier.code if isinstance(v, HRIComponentProfile) else str(v),
)
def test_function(profile: HRIComponentProfile, function: ComponentFunction | None) -> None:
    """The function is the RoSO class of the type, empty where the ontology has none."""
    assert profile.function == function


def test_navigation_parameters() -> None:
    """Navigation declares its three parameters with the XML defaults."""
    defaults = {p.name: p.default_value for p in NAVIGATION_PROFILE.parameter_profiles}
    assert defaults == {"target_positions": "", "time_limit": "0", "routing_policy": "time"}


def test_speech_synthesis_messages() -> None:
    """SpeechSynthesis adds two queries and five parameters, with the XML defaults."""
    assert _names(SPEECH_SYNTHESIS_PROFILE.query_profiles) == [
        "component_status",
        "synthesizable_languages",
        "available_voices",
    ]
    results = [q.results[0] for q in SPEECH_SYNTHESIS_PROFILE.query_profiles[1:]]
    assert [(r.name, r.data_type_ref.code) for r in results] == [
        ("languages", "string[]"),
        ("characters", "string[]"),
    ]
    assert SPEECH_SYNTHESIS_PROFILE.event_profiles == []
    types = {p.name: p.data_type_ref.code for p in SPEECH_SYNTHESIS_PROFILE.parameter_profiles}
    defaults = {p.name: p.default_value for p in SPEECH_SYNTHESIS_PROFILE.parameter_profiles}
    assert types == {
        "speech_text": "string",
        "ssml_text": "string",
        "volume": "int",
        "language": "string",
        "character": "string",
    }
    assert defaults == {
        "speech_text": "",
        "ssml_text": "",
        "volume": "50",
        "language": "en",
        "character": "default",
    }


def test_profiles_document() -> None:
    """profiles.json lists every constant by name, in a fixed order, as JSON values."""
    document = profiles_document()
    entries = document["profiles"]
    assert isinstance(entries, list)
    assert [entry["name"] for entry in entries] == [
        "ROIS_COMMON_PROFILE",
        "NAVIGATION_PROFILE",
        "PERSON_DETECTION_PROFILE",
        "REACTION_PROFILE",
        "SPEECH_SYNTHESIS_PROFILE",
        "SYSTEM_INFORMATION_PROFILE",
    ]
    assert entries[1]["profile"] == NAVIGATION_PROFILE.model_dump(mode="json")
