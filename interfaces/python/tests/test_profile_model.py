"""Tests for the profile model of the XML codec work (stream I, step 1).

Query and event profiles carry arguments, a parameter without a default has the
default None, a parameter can be read-only, ConcurrentCommands holds branches, and the
enumerations carry the literals of the IDL.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from openrois.interfaces.catalog import EXTENSIONS
from openrois.interfaces.common import ComponentStatus, StreamStatus
from openrois.interfaces.hri import (
    Branch,
    CommandUnit,
    CommandUnitSequence,
    ConcurrentCommands,
    ReturnCode,
)
from openrois.interfaces.profiles import (
    EventMessageProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from tests._normative import NORMATIVE_DIR, requires_normative


def _param(name: str, code: str = "String") -> ParameterProfile:
    return ParameterProfile(name=name, data_type_ref=RoISIdentifierType(code=code))


def _unit(command_type: str) -> CommandUnit:
    return CommandUnit(component_ref="c", command_type=command_type, command_id="")


class TestQueryAndEventArguments:
    """Validation row 9: query and event profiles carry an arguments list."""

    def test_query_profile_has_arguments(self) -> None:
        query = QueryMessageProfile(
            name="get_stream_status",
            arguments=[_param("stream_id")],
            results=[_param("status", "Stream_Status")],
        )
        assert [a.name for a in query.arguments] == ["stream_id"]

    def test_event_profile_has_arguments(self) -> None:
        event = EventMessageProfile(name="notify_stream_status", arguments=[_param("stream_id")])
        assert [a.name for a in event.arguments] == ["stream_id"]

    def test_arguments_default_to_empty(self) -> None:
        assert QueryMessageProfile(name="q").arguments == []
        assert EventMessageProfile(name="e").arguments == []


class TestParameterDefault:
    """Validation row 22: no default_value, or an empty one, means no default."""

    def test_default_is_none_when_absent(self) -> None:
        assert _param("p").default_value is None

    def test_default_keeps_a_given_value(self) -> None:
        param = ParameterProfile(
            name="time_limit", data_type_ref=RoISIdentifierType(code="int"), default_value="0"
        )
        assert param.default_value == "0"

    def test_empty_default_reads_as_none(self) -> None:
        param = ParameterProfile(
            name="threshold", data_type_ref=RoISIdentifierType(code="int"), default_value=""
        )
        assert param.default_value is None


class TestReadOnly:
    """Validation rows 10 and 25: a parameter the spec lists only under get_parameter."""

    def test_read_only_defaults_to_false(self) -> None:
        assert _param("p").read_only is False

    def test_read_only_can_be_set(self) -> None:
        param = ParameterProfile(
            name="available_encodings",
            data_type_ref=RoISIdentifierType(code="String"),
            read_only=True,
        )
        assert param.read_only is True

    def test_read_only_is_a_registered_extension(self) -> None:
        assert any(e.model == "ParameterProfile" and e.field == "read_only" for e in EXTENSIONS)


class TestBranches:
    """Validation row 3: ConcurrentCommands holds branches, each an ordered command list."""

    def test_branches_hold_ordered_command_lists(self) -> None:
        group = ConcurrentCommands(
            branch_list=[
                Branch(command_list=[_unit("C"), _unit("D")]),
                Branch(command_list=[_unit("E")]),
            ]
        )
        assert [[u.command_type for u in b.command_list] for b in group.branch_list] == [
            ["C", "D"],
            ["E"],
        ]

    def test_flat_command_list_reads_as_one_command_branches(self) -> None:
        group = ConcurrentCommands.model_validate(
            {"command_list": [_unit("C").model_dump(), _unit("E").model_dump()], "delay_time": 5}
        )
        assert group.branch_list == [
            Branch(command_list=[_unit("C")]),
            Branch(command_list=[_unit("E")]),
        ]
        assert group.delay_time == 5

    def test_both_forms_together_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            ConcurrentCommands.model_validate(
                {
                    "command_list": [_unit("C").model_dump()],
                    "branch_list": [{"command_list": [_unit("E").model_dump()]}],
                }
            )

    def test_a_branch_needs_a_command(self) -> None:
        with pytest.raises(ValidationError):
            Branch(command_list=[])

    def test_sequence_reads_a_flat_group(self) -> None:
        sequence = CommandUnitSequence.model_validate(
            {
                "command_unit_list": [
                    _unit("A").model_dump(),
                    {"command_list": [_unit("B").model_dump()]},
                ]
            }
        )
        group = sequence.command_unit_list[1]
        assert isinstance(group, ConcurrentCommands)
        assert group.branch_list == [Branch(command_list=[_unit("B")])]

    def test_dump_uses_branch_list(self) -> None:
        group = ConcurrentCommands(branch_list=[Branch(command_list=[_unit("C")])])
        assert set(group.model_dump()) == {"branch_list", "delay_time"}


class TestEnumerations:
    def test_return_code_keeps_unsupported(self) -> None:
        assert ReturnCode.UNSUPPORTED == "UNSUPPORTED"


def _idl_enum(filename: str, name: str) -> list[str]:
    text = (NORMATIVE_DIR / filename).read_text()
    block = re.search(rf"enum\s+{name}\s*\{{(.*?)\}}", text, re.DOTALL)
    assert block is not None, f"enum {name} not found in {filename}"
    return [item.strip() for item in block.group(1).split(",") if item.strip()]


@requires_normative
class TestEnumerationLiterals:
    """Component_Status and Stream_Status carry the literals of RoIS_Common.idl."""

    def test_component_status(self) -> None:
        literals = _idl_enum("RoIS_Common.idl", "Component_Status")
        assert [s.value for s in ComponentStatus] == literals

    def test_stream_status(self) -> None:
        literals = _idl_enum("RoIS_Common.idl", "Stream_Status")
        assert [s.value for s in StreamStatus] == literals

    def test_return_code(self) -> None:
        literals = _idl_enum("RoIS_HRI.idl", "ReturnCode_t")
        assert [c.value for c in ReturnCode] == literals
