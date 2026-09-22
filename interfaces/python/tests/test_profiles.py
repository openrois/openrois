"""Tests for openrois.interfaces.profiles — Profile schema models."""

import pytest

from openrois.interfaces.profiles import (
    CommandMessageProfile,
    EventMessageProfile,
    HRIComponentProfile,
    HRIEngineProfileType,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)


class TestRoISIdentifierType:
    def test_minimal(self) -> None:
        id_type = RoISIdentifierType(code="PersonDetection")
        assert id_type.code == "PersonDetection"
        assert id_type.authority == ""
        assert id_type.codebook_ref == ""
        assert id_type.version == ""

    def test_full(self) -> None:
        id_type = RoISIdentifierType(
            authority="OMG",
            code="PersonDetection",
            codebook_ref="https://www.omg.org/spec/RoIS/",
            version="2.0",
        )
        assert id_type.authority == "OMG"
        assert id_type.code == "PersonDetection"
        assert id_type.version == "2.0"

    def test_frozen(self) -> None:
        id_type = RoISIdentifierType(code="Navigation")
        with pytest.raises(Exception):
            id_type.code = "changed"  # type: ignore[misc]

    def test_json_round_trip(self) -> None:
        id_type = RoISIdentifierType(authority="OMG", code="FaceDetection", version="2.0")
        j = id_type.model_dump_json()
        id_type2 = RoISIdentifierType.model_validate_json(j)
        assert id_type == id_type2


class TestParameterProfile:
    def test_minimal(self) -> None:
        pp = ParameterProfile(
            name="number",
            data_type_ref=RoISIdentifierType(code="int"),
        )
        assert pp.name == "number"
        assert pp.data_type_ref.code == "int"
        assert pp.default_value == ""
        assert pp.description == ""

    def test_with_defaults(self) -> None:
        pp = ParameterProfile(
            name="time_limit",
            data_type_ref=RoISIdentifierType(code="int"),
            default_value="0",
            description="Intended time limit to complete navigation",
        )
        assert pp.default_value == "0"
        assert "time limit" in pp.description.lower()


class TestMessageProfiles:
    def test_command_message_profile(self) -> None:
        cmd = CommandMessageProfile(
            name="set_parameter",
            arguments=[
                ParameterProfile(
                    name="target_positions",
                    data_type_ref=RoISIdentifierType(code="string[]"),
                    description="Navigation target positions",
                ),
            ],
            results=[
                ParameterProfile(
                    name="command_id",
                    data_type_ref=RoISIdentifierType(code="string"),
                ),
            ],
            timeout=5000,
        )
        assert cmd.name == "set_parameter"
        assert len(cmd.arguments) == 1
        assert len(cmd.results) == 1
        assert cmd.timeout == 5000

    def test_query_message_profile(self) -> None:
        query = QueryMessageProfile(
            name="component_status",
            results=[
                ParameterProfile(
                    name="status",
                    data_type_ref=RoISIdentifierType(code="Component_Status"),
                ),
            ],
        )
        assert query.name == "component_status"
        assert len(query.results) == 1

    def test_event_message_profile(self) -> None:
        event = EventMessageProfile(
            name="person_detected",
            results=[
                ParameterProfile(
                    name="number",
                    data_type_ref=RoISIdentifierType(code="int"),
                    description="Number of detected persons",
                ),
                ParameterProfile(
                    name="timestamp",
                    data_type_ref=RoISIdentifierType(code="DateTime"),
                    description="Time when measured",
                ),
            ],
        )
        assert event.name == "person_detected"
        assert len(event.results) == 2


class TestHRIComponentProfile:
    def test_person_detection_profile(self) -> None:
        profile = HRIComponentProfile(
            identifier=RoISIdentifierType(authority="OMG", code="PersonDetection"),
            name="person_detecter",
            sub_component_profiles=["urn:x-rois:def:Component:OMG::RoISCommon"],
            event_profiles=[
                EventMessageProfile(
                    name="person_detected",
                    results=[
                        ParameterProfile(
                            name="number",
                            data_type_ref=RoISIdentifierType(code="int"),
                            description="number of detected persons",
                        ),
                        ParameterProfile(
                            name="timestamp",
                            data_type_ref=RoISIdentifierType(code="DateTime"),
                            description="time when measured",
                        ),
                    ],
                ),
            ],
        )
        assert profile.identifier.code == "PersonDetection"
        assert profile.name == "person_detecter"
        assert len(profile.event_profiles) == 1
        assert profile.event_profiles[0].name == "person_detected"

    def test_navigation_profile(self) -> None:
        profile = HRIComponentProfile(
            identifier=RoISIdentifierType(authority="OMG", code="Navigation"),
            name="navigation",
            sub_component_profiles=["urn:x-rois:def:Component:OMG::RoISCommon"],
            command_profiles=[
                CommandMessageProfile(
                    name="set_parameter",
                    arguments=[
                        ParameterProfile(
                            name="target_positions",
                            data_type_ref=RoISIdentifierType(code="string[]"),
                            description="navigation target positions",
                        ),
                        ParameterProfile(
                            name="time_limit",
                            data_type_ref=RoISIdentifierType(code="int"),
                            default_value="0",
                            description="intended time limit to complete navigation",
                        ),
                        ParameterProfile(
                            name="routing_policy",
                            data_type_ref=RoISIdentifierType(code="string"),
                            default_value="time",
                            description="routing policy: 'time' priority or 'distance' priority",
                        ),
                    ],
                ),
            ],
            event_profiles=[
                EventMessageProfile(
                    name="reached_target",
                    results=[
                        ParameterProfile(
                            name="target",
                            data_type_ref=RoISIdentifierType(code="string"),
                            description="reached target destination",
                        ),
                        ParameterProfile(
                            name="is_final_target",
                            data_type_ref=RoISIdentifierType(code="bool"),
                            description="if it is final destination point",
                        ),
                    ],
                ),
            ],
            parameter_profiles=[
                ParameterProfile(
                    name="target_positions",
                    data_type_ref=RoISIdentifierType(code="string[]"),
                    description="navigation target positions",
                ),
                ParameterProfile(
                    name="time_limit",
                    data_type_ref=RoISIdentifierType(code="int"),
                    default_value="0",
                    description="intended time limit to complete navigation",
                ),
                ParameterProfile(
                    name="routing_policy",
                    data_type_ref=RoISIdentifierType(code="string"),
                    default_value="time",
                    description="routing policy: 'time' priority or 'distance' priority",
                ),
            ],
        )
        assert profile.identifier.code == "Navigation"
        assert len(profile.command_profiles) == 1
        assert len(profile.event_profiles) == 1
        assert len(profile.parameter_profiles) == 3

    def test_json_round_trip(self) -> None:
        profile = HRIComponentProfile(
            identifier=RoISIdentifierType(authority="OMG", code="SystemInformation"),
            name="system_info",
            query_profiles=[
                QueryMessageProfile(
                    name="robot_position",
                    results=[
                        ParameterProfile(
                            name="position_data",
                            data_type_ref=RoISIdentifierType(code="String[]"),
                            description="position of robot or its parts",
                        ),
                    ],
                ),
            ],
        )
        j = profile.model_dump_json()
        profile2 = HRIComponentProfile.model_validate_json(j)
        assert profile == profile2


class TestHRIEngineProfileType:
    def test_minimal(self) -> None:
        profile = HRIEngineProfileType(
            identifier=RoISIdentifierType(authority="OMG", code="HRI_Engine"),
        )
        assert profile.identifier.code == "HRI_Engine"
        assert profile.sub_profiles == []
        assert profile.component_ids == []
        assert profile.parameter_profiles == []

    def test_with_components(self) -> None:
        profile = HRIEngineProfileType(
            identifier=RoISIdentifierType(authority="OMG", code="HRI_Engine"),
            component_ids=["robot-a1/pd", "robot-a1/nav"],
        )
        assert len(profile.component_ids) == 2
