"""Tests for MockSystemInformation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from openrois.interfaces.hri import Parameter, Result

from openrois.components.common import MockSystemInformation


@dataclass
class Binding:
    """The engine side of the component in these tests."""

    ref: str = "robot_1/system_information"
    events: list[tuple[str, Sequence[Result]]] = field(default_factory=list)

    def parameters(self) -> Sequence[Parameter]:
        return []

    def emit(self, event_type: str, results: Sequence[Result]) -> None:
        self.events.append((event_type, results))


def test_serves_the_two_queries() -> None:
    profile = MockSystemInformation.rois_profile()
    assert [q.name for q in profile.query_profiles] == ["robot_position", "engine_status"]
    assert profile.command_profiles == []


async def test_robot_position() -> None:
    info = MockSystemInformation()
    info.rois_bind(Binding())
    results = {r.name: r for r in await info.rois_query("robot_position")}
    assert results["position_data"].value == '["0.0,0.0,0.0"]'
    assert results["robot_ref"].value == '["robot_1"]'
    assert results["timestamp"].data_type_ref == "DateTime"


async def test_engine_status() -> None:
    results = await MockSystemInformation().rois_query("engine_status")
    assert [(r.name, r.value) for r in results][1] == ("status", "READY")
