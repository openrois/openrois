"""Tests for openrois.interfaces.components.navigation — Navigation typed models."""

import pytest

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components.navigation import (
    NAVIGATION_URN,
    NavigationGetParameterResult,
    NavigationReachedTargetEvent,
    NavigationSetParameter,
    NavigationSetParameterResult,
    NavigationStatusResult,
)


class TestNavigationURN:
    def test_urn_value(self) -> None:
        assert NAVIGATION_URN == "urn:x-rois:def:component:OMG::Navigation"


class TestNavigationSetParameter:
    def test_construction_with_defaults(self) -> None:
        cmd = NavigationSetParameter(target_positions=["1.0,2.0,0.0"])
        assert cmd.target_positions == ["1.0,2.0,0.0"]
        assert cmd.time_limit == 0
        assert cmd.routing_policy == "time"

    def test_construction_full(self) -> None:
        cmd = NavigationSetParameter(
            target_positions=["1.0,2.0,0.0", "3.0,4.0,1.5"],
            time_limit=30,
            routing_policy="distance",
        )
        assert len(cmd.target_positions) == 2
        assert cmd.time_limit == 30
        assert cmd.routing_policy == "distance"

    def test_serialization(self) -> None:
        cmd = NavigationSetParameter(
            target_positions=["1.0,2.0,0.0"],
            time_limit=60,
            routing_policy="time",
        )
        d = cmd.model_dump()
        assert d["target_positions"] == ["1.0,2.0,0.0"]
        assert d["time_limit"] == 60
        assert d["routing_policy"] == "time"

    def test_json_round_trip(self) -> None:
        cmd = NavigationSetParameter(
            target_positions=["1.0,2.0,0.0"],
            time_limit=45,
            routing_policy="distance",
        )
        j = cmd.model_dump_json()
        cmd2 = NavigationSetParameter.model_validate_json(j)
        assert cmd == cmd2


class TestNavigationSetParameterResult:
    def test_construction(self) -> None:
        result = NavigationSetParameterResult(command_id="cmd-nav-001")
        assert result.command_id == "cmd-nav-001"

    def test_frozen(self) -> None:
        result = NavigationSetParameterResult(command_id="cmd-nav-001")
        with pytest.raises(Exception):
            result.command_id = "changed"  # type: ignore[misc]


class TestNavigationGetParameterResult:
    def test_construction(self) -> None:
        result = NavigationGetParameterResult(
            target_positions=["1.0,2.0,0.0"],
            time_limit=30,
            routing_policy="time",
        )
        assert result.target_positions == ["1.0,2.0,0.0"]
        assert result.time_limit == 30
        assert result.routing_policy == "time"

    def test_json_round_trip(self) -> None:
        result = NavigationGetParameterResult(
            target_positions=["3.0,4.0,1.5"],
            time_limit=60,
            routing_policy="distance",
        )
        j = result.model_dump_json()
        result2 = NavigationGetParameterResult.model_validate_json(j)
        assert result == result2


class TestNavigationStatusResult:
    def test_construction(self) -> None:
        result = NavigationStatusResult(status=ComponentStatus.READY)
        assert result.status == ComponentStatus.READY

    def test_serialization(self) -> None:
        result = NavigationStatusResult(status=ComponentStatus.BUSY)
        d = result.model_dump()
        assert d["status"] == "BUSY"


class TestNavigationReachedTargetEvent:
    def test_construction(self) -> None:
        event = NavigationReachedTargetEvent(
            target="waypoint-1",
            is_final_target=False,
        )
        assert event.target == "waypoint-1"
        assert event.is_final_target is False

    def test_final_target(self) -> None:
        event = NavigationReachedTargetEvent(
            target="destination",
            is_final_target=True,
        )
        assert event.is_final_target is True

    def test_serialization(self) -> None:
        event = NavigationReachedTargetEvent(
            target="waypoint-2",
            is_final_target=True,
        )
        d = event.model_dump()
        assert d["target"] == "waypoint-2"
        assert d["is_final_target"] is True

    def test_json_round_trip(self) -> None:
        event = NavigationReachedTargetEvent(
            target="waypoint-3",
            is_final_target=False,
        )
        j = event.model_dump_json()
        event2 = NavigationReachedTargetEvent.model_validate_json(j)
        assert event == event2

    def test_frozen(self) -> None:
        event = NavigationReachedTargetEvent(target="wp", is_final_target=True)
        with pytest.raises(Exception):
            event.target = "changed"  # type: ignore[misc]
