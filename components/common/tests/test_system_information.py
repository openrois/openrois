"""Tests for MockSystemInformation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.hri import Parameter, Result

from openrois.components.common import MockSystemInformation


@dataclass
class Binding:
    """The engine side of the component in these tests."""

    ref: str = "robot_1/system_information"
    events: list[tuple[str, Sequence[Result]]] = field(default_factory=list)
    engine: ComponentStatus = ComponentStatus.READY

    def parameters(self) -> Sequence[Parameter]:
        return []

    def emit(
        self,
        event_type: str,
        results: Sequence[Result],
        concerning: Mapping[str, str] | None = None,
    ) -> None:
        self.events.append((event_type, results))

    def raise_status(self, status: ComponentStatus, message: str) -> None:
        raise AssertionError("SystemInformation raises no status in these tests")

    def clear_status(self) -> None:
        raise AssertionError("SystemInformation clears no status in these tests")

    def engine_status(self) -> ComponentStatus:
        return self.engine


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


async def test_item_11_engine_status_reports_the_status_of_the_engine() -> None:
    info = MockSystemInformation()
    binding = Binding()
    info.rois_bind(binding)
    results = await info.rois_query("engine_status")
    assert [(r.name, r.value) for r in results][1] == ("status", "READY")
    binding.engine = ComponentStatus.WARNING
    results = await info.rois_query("engine_status")
    assert [(r.name, r.value) for r in results][1] == ("status", "WARNING")


def test_item_11_serves_no_component_status() -> None:
    profile = MockSystemInformation.rois_profile()
    assert "component_status" not in [q.name for q in profile.query_profiles]
    assert profile.sub_component_profiles == []
