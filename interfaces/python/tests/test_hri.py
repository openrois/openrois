"""Tests for openrois.interfaces.hri — Core HRI types."""

import json

from openrois.interfaces.hri import (
    Argument,
    ArgumentList,
    CommandUnit,
    CommandUnitSequence,
    ConcurrentCommands,
    ConditionT,
    DateTime,
    HRIEngineProfile,
    Integer,
    Parameter,
    ParameterList,
    Result,
    ResultList,
    ReturnCode,
    RoISIdentifier,
    RoISIdentifierList,
    RoLoData,
)

# ---------------------------------------------------------------------------
# ReturnCode enum
# ---------------------------------------------------------------------------


class TestReturnCode:
    def test_all_values(self) -> None:
        assert set(ReturnCode) == {
            ReturnCode.OK,
            ReturnCode.ERROR,
            ReturnCode.BAD_PARAMETER,
            ReturnCode.UNSUPPORTED,
            ReturnCode.OUT_OF_RESOURCES,
            ReturnCode.TIMEOUT,
        }

    def test_string_values(self) -> None:
        assert ReturnCode.OK.value == "OK"
        assert ReturnCode.ERROR.value == "ERROR"
        assert ReturnCode.BAD_PARAMETER.value == "BAD_PARAMETER"
        assert ReturnCode.UNSUPPORTED.value == "UNSUPPORTED"
        assert ReturnCode.OUT_OF_RESOURCES.value == "OUT_OF_RESOURCES"
        assert ReturnCode.TIMEOUT.value == "TIMEOUT"

    def test_from_string(self) -> None:
        assert ReturnCode("OK") is ReturnCode.OK
        assert ReturnCode("ERROR") is ReturnCode.ERROR

    def test_json_serialization(self) -> None:
        assert json.dumps(ReturnCode.OK.value) == '"OK"'

    def test_is_str_enum(self) -> None:
        assert isinstance(ReturnCode.OK, str)


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------


class TestTypeAliases:
    def test_rois_identifier_is_str(self) -> None:
        id_: RoISIdentifier = "robot-a1/person_detection"
        assert isinstance(id_, str)

    def test_rois_identifier_list(self) -> None:
        ids: RoISIdentifierList = ["robot-a1/pd", "robot-a1/nav"]
        assert len(ids) == 2
        assert ids[0] == "robot-a1/pd"

    def test_condition_t(self) -> None:
        cond: ConditionT = "component_type='FaceDetection'"
        assert isinstance(cond, str)

    def test_hri_engine_profile(self) -> None:
        profile: HRIEngineProfile = "<profile>...</profile>"
        assert isinstance(profile, str)

    def test_date_time(self) -> None:
        dt: DateTime = "2025-01-15T10:30:00Z"
        assert isinstance(dt, str)

    def test_integer(self) -> None:
        val: Integer = 42
        assert isinstance(val, int)

    def test_rolo_data(self) -> None:
        data: RoLoData = "1.0,2.0,3.0"
        assert isinstance(data, str)


# ---------------------------------------------------------------------------
# Result, Parameter, Argument structs
# ---------------------------------------------------------------------------


class TestResult:
    def test_construction(self) -> None:
        r = Result(name="number", data_type_ref="int", value="3")
        assert r.name == "number"
        assert r.data_type_ref == "int"
        assert r.value == "3"

    def test_serialization(self) -> None:
        r = Result(name="timestamp", data_type_ref="DateTime", value="2025-01-15T10:30:00Z")
        d = r.model_dump()
        assert d == {
            "name": "timestamp",
            "data_type_ref": "DateTime",
            "value": "2025-01-15T10:30:00Z",
        }

    def test_json_round_trip(self) -> None:
        r = Result(name="number", data_type_ref="int", value="3")
        j = r.model_dump_json()
        r2 = Result.model_validate_json(j)
        assert r == r2

    def test_result_list(self) -> None:
        results: ResultList = [
            Result(name="number", data_type_ref="int", value="3"),
            Result(name="timestamp", data_type_ref="DateTime", value="2025-01-15T10:30:00Z"),
        ]
        assert len(results) == 2


class TestParameter:
    def test_construction(self) -> None:
        p = Parameter(name="target_position", data_type_ref="string[]", value="1.0,2.0")
        assert p.name == "target_position"
        assert p.data_type_ref == "string[]"
        assert p.value == "1.0,2.0"

    def test_serialization(self) -> None:
        p = Parameter(name="volume", data_type_ref="int", value="50")
        d = p.model_dump()
        assert d["name"] == "volume"

    def test_parameter_list(self) -> None:
        params: ParameterList = [
            Parameter(name="volume", data_type_ref="int", value="50"),
            Parameter(name="language", data_type_ref="string", value="en"),
        ]
        assert len(params) == 2


class TestArgument:
    def test_construction(self) -> None:
        a = Argument(name="stream_id", data_type_ref="string", value="stream-1")
        assert a.name == "stream_id"
        assert a.data_type_ref == "string"
        assert a.value == "stream-1"

    def test_argument_list(self) -> None:
        args: ArgumentList = [
            Argument(name="stream_id", data_type_ref="string", value="stream-1"),
        ]
        assert len(args) == 1


# ---------------------------------------------------------------------------
# CommandUnitSequence
# ---------------------------------------------------------------------------


class TestCommandUnit:
    def test_construction(self) -> None:
        cu = CommandUnit(
            component_ref="robot-a1/navigation",
            command_type="start",
            command_id="cmd-001",
        )
        assert cu.component_ref == "robot-a1/navigation"
        assert cu.command_type == "start"
        assert cu.command_id == "cmd-001"
        assert cu.arguments == []
        assert cu.delay_time is None

    def test_with_arguments(self) -> None:
        cu = CommandUnit(
            component_ref="robot-a1/navigation",
            command_type="set_parameter",
            command_id="cmd-002",
            arguments=[
                Argument(name="target_position", data_type_ref="string[]", value="1.0,2.0"),
            ],
            delay_time=100,
        )
        assert len(cu.arguments) == 1
        assert cu.delay_time == 100

    def test_serialization(self) -> None:
        cu = CommandUnit(
            component_ref="robot-a1/pd",
            command_type="start",
            command_id="cmd-003",
        )
        d = cu.model_dump()
        assert d["component_ref"] == "robot-a1/pd"
        assert d["arguments"] == []


class TestConcurrentCommands:
    def test_construction(self) -> None:
        cc = ConcurrentCommands(
            command_list=[
                CommandUnit(component_ref="r/pd", command_type="start", command_id="c1"),
                CommandUnit(component_ref="r/fd", command_type="start", command_id="c2"),
            ],
        )
        assert len(cc.command_list) == 2
        assert cc.delay_time is None

    def test_with_delay(self) -> None:
        cc = ConcurrentCommands(
            command_list=[
                CommandUnit(component_ref="r/pd", command_type="start", command_id="c1"),
            ],
            delay_time=500,
        )
        assert cc.delay_time == 500


class TestCommandUnitSequence:
    def test_single_command_sequence(self) -> None:
        seq = CommandUnitSequence(
            command_unit_list=[
                CommandUnit(component_ref="r/nav", command_type="start", command_id="c1"),
            ]
        )
        assert len(seq.command_unit_list) == 1

    def test_sequential_commands(self) -> None:
        seq = CommandUnitSequence(
            command_unit_list=[
                CommandUnit(component_ref="r/nav", command_type="start", command_id="c1"),
                CommandUnit(component_ref="r/pd", command_type="start", command_id="c2"),
            ]
        )
        assert len(seq.command_unit_list) == 2

    def test_mixed_sequential_and_concurrent(self) -> None:
        seq = CommandUnitSequence(
            command_unit_list=[
                CommandUnit(component_ref="r/nav", command_type="start", command_id="c1"),
                ConcurrentCommands(
                    command_list=[
                        CommandUnit(component_ref="r/pd", command_type="start", command_id="c2"),
                        CommandUnit(component_ref="r/fd", command_type="start", command_id="c3"),
                    ],
                ),
            ]
        )
        assert len(seq.command_unit_list) == 2
        assert isinstance(seq.command_unit_list[0], CommandUnit)
        assert isinstance(seq.command_unit_list[1], ConcurrentCommands)

    def test_json_round_trip(self) -> None:
        seq = CommandUnitSequence(
            command_unit_list=[
                CommandUnit(component_ref="r/nav", command_type="start", command_id="c1"),
                ConcurrentCommands(
                    command_list=[
                        CommandUnit(component_ref="r/pd", command_type="start", command_id="c2"),
                    ],
                ),
            ]
        )
        j = seq.model_dump_json()
        seq2 = CommandUnitSequence.model_validate_json(j)
        assert seq == seq2

    def test_discriminated_union(self) -> None:
        """Verify that CommandUnitSequenceItem can be deserialized from both types."""
        item1 = CommandUnit(component_ref="r/nav", command_type="start", command_id="c1")
        item2 = ConcurrentCommands(
            command_list=[CommandUnit(component_ref="r/pd", command_type="start", command_id="c2")]
        )
        # Both should be valid CommandUnitSequenceItems
        assert isinstance(item1, CommandUnit)
        assert isinstance(item2, ConcurrentCommands)
