"""Tests for openrois.interfaces.components.system_information — SystemInformation typed models."""

import pytest
from pydantic import ValidationError

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components.system_information import (
    SYSTEM_INFORMATION_URN,
    SystemInformationEngineStatusResult,
    SystemInformationRobotPositionResult,
)


class TestSystemInformationURN:
    def test_urn_value(self) -> None:
        assert SYSTEM_INFORMATION_URN == "urn:x-rois:def:component:OMG::SystemInformation"


class TestSystemInformationRobotPositionResult:
    def test_construction(self) -> None:
        result = SystemInformationRobotPositionResult(
            timestamp="2025-01-15T10:30:00Z",
            robot_ref=["robot-a1", "robot-a2"],
            position_data=["1.0,2.0,0.0", "3.0,4.0,1.5"],
        )
        assert result.timestamp == "2025-01-15T10:30:00Z"
        assert result.robot_ref == ["robot-a1", "robot-a2"]
        assert result.position_data == ["1.0,2.0,0.0", "3.0,4.0,1.5"]

    def test_serialization(self) -> None:
        result = SystemInformationRobotPositionResult(
            timestamp="2025-01-15T10:30:00Z",
            robot_ref=["robot-a1"],
            position_data=["1.0,2.0,0.0"],
        )
        d = result.model_dump()
        assert d == {
            "timestamp": "2025-01-15T10:30:00Z",
            "robot_ref": ["robot-a1"],
            "position_data": ["1.0,2.0,0.0"],
        }

    def test_json_round_trip(self) -> None:
        result = SystemInformationRobotPositionResult(
            timestamp="2025-01-15T10:30:00Z",
            robot_ref=["robot-a1", "robot-a2"],
            position_data=["1.0,2.0,0.0"],
        )
        j = result.model_dump_json()
        result2 = SystemInformationRobotPositionResult.model_validate_json(j)
        assert result == result2

    def test_frozen(self) -> None:
        result = SystemInformationRobotPositionResult(
            timestamp="2025-01-15T10:30:00Z",
            robot_ref=["robot-a1"],
            position_data=["1.0,2.0,0.0"],
        )
        with pytest.raises(ValidationError):
            result.timestamp = "changed"  # type: ignore[misc]

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            SystemInformationRobotPositionResult(
                timestamp="2025-01-15T10:30:00Z",
                robot_ref=["robot-a1"],
                position_data=["1.0,2.0,0.0"],
                unexpected="field",  # type: ignore[call-arg]
            )

    def test_empty_robot_ref(self) -> None:
        """Edge case: empty robot_ref list."""
        result = SystemInformationRobotPositionResult(
            timestamp="2025-01-15T10:30:00Z",
            robot_ref=[],
            position_data=[],
        )
        assert result.robot_ref == []
        assert result.position_data == []


class TestSystemInformationEngineStatusResult:
    def test_construction(self) -> None:
        result = SystemInformationEngineStatusResult(
            status=ComponentStatus.READY,
            operable_time=["2025-01-15T08:00:00Z", "2025-01-15T12:00:00Z"],
        )
        assert result.status == ComponentStatus.READY
        assert result.operable_time == ["2025-01-15T08:00:00Z", "2025-01-15T12:00:00Z"]

    def test_serialization(self) -> None:
        result = SystemInformationEngineStatusResult(
            status=ComponentStatus.BUSY,
            operable_time=["2025-01-15T08:00:00Z"],
        )
        d = result.model_dump()
        assert d["status"] == "BUSY"
        assert d["operable_time"] == ["2025-01-15T08:00:00Z"]

    def test_json_round_trip(self) -> None:
        result = SystemInformationEngineStatusResult(
            status=ComponentStatus.ERROR,
            operable_time=["2025-01-15T08:00:00Z", "2025-01-15T16:00:00Z"],
        )
        j = result.model_dump_json()
        result2 = SystemInformationEngineStatusResult.model_validate_json(j)
        assert result == result2

    def test_frozen(self) -> None:
        result = SystemInformationEngineStatusResult(
            status=ComponentStatus.READY,
            operable_time=["2025-01-15T08:00:00Z"],
        )
        with pytest.raises(ValidationError):
            result.status = ComponentStatus.ERROR  # type: ignore[misc]

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            SystemInformationEngineStatusResult(
                status=ComponentStatus.READY,
                operable_time=["2025-01-15T08:00:00Z"],
                unexpected="field",  # type: ignore[call-arg]
            )

    def test_empty_operable_time(self) -> None:
        """Edge case: empty operable_time list."""
        result = SystemInformationEngineStatusResult(
            status=ComponentStatus.UNINITIALIZED,
            operable_time=[],
        )
        assert result.operable_time == []
