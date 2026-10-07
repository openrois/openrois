"""The gRPC components against a stand-in for the Kachaka gRPC API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from openrois.components.kachaka import GrpcNavigation, GrpcSystemInformation
from tests._fakes import FakeKachaka

type Host = Callable[..., Any]


@pytest.fixture
def kachaka(monkeypatch: pytest.MonkeyPatch) -> FakeKachaka:
    fake = FakeKachaka()
    fake.install(monkeypatch)
    return fake


async def navigation(host: Host, target: str = "kitchen") -> Any:
    robot = await host("navigation", GrpcNavigation("10.0.0.2:26400", auto_homing=True))
    result = await robot.call(
        "rois.command.set_parameter",
        component_ref=robot.ref,
        parameters=[{"name": "target_positions", "data_type_ref": "", "value": f'["{target}"]'}],
    )
    assert await robot.completed(result["command_id"]) == "OK"
    subscribed = await robot.call(
        "rois.event.subscribe",
        event_type="reached_target",
        condition=f"component_ref = '{robot.ref}'",
    )
    assert subscribed["return_code"] == "OK"
    return robot


def test_serves_start_stop_and_reached_target() -> None:
    profile = GrpcNavigation.rois_profile()
    assert [c.name for c in profile.command_profiles] == ["start", "stop"]
    assert [e.name for e in profile.event_profiles] == ["reached_target"]


async def test_start_drives_to_the_location_and_reports_the_arrival(
    host: Host, kachaka: FakeKachaka
) -> None:
    robot = await navigation(host)
    assert kachaka.auto_homing is True
    await robot.execute("start", "c1")
    await asyncio.sleep(0.01)
    assert kachaka.moves == ["L1"]
    kachaka.arrive.set()
    assert await robot.completed("c1") == "OK"
    [event] = robot.sent("rois.event.notify_event")
    assert {r["name"]: r["value"] for r in event["results"]} == {
        "target": "kitchen",
        "is_final_target": "true",
    }


async def test_a_location_is_found_by_its_id_too(host: Host, kachaka: FakeKachaka) -> None:
    robot = await navigation(host, target="L1")
    kachaka.arrive.set()
    await robot.execute("start", "c1")
    assert await robot.completed("c1") == "OK"
    assert kachaka.moves == ["L1"]


async def test_an_unknown_location_fails_the_start(host: Host, kachaka: FakeKachaka) -> None:
    robot = await navigation(host, target="garage")
    await robot.execute("start", "c1")
    assert await robot.completed("c1") == "ERROR"
    assert kachaka.moves == []


async def test_a_failed_drive_ends_with_error(host: Host, kachaka: FakeKachaka) -> None:
    kachaka.succeed = False
    kachaka.arrive.set()
    robot = await navigation(host)
    await robot.execute("start", "c1")
    assert await robot.completed("c1") == "ERROR"
    assert robot.sent("rois.event.notify_event") == []


async def test_stop_halts_the_robot_before_the_drive_ends(
    host: Host, kachaka: FakeKachaka
) -> None:
    robot = await navigation(host)
    await robot.execute("start", "c1")
    await asyncio.sleep(0.01)
    await robot.execute("stop", "c2")
    assert await robot.completed("c2") == "OK"
    assert await robot.completed("c1") == "ABORT"
    # The stop handler halts the robot, then the engine cancels the drive.
    assert kachaka.log[:3] == ["move L1", "cancel", "cancelled L1"]
    assert robot.sent("rois.event.notify_event") == []


async def test_a_new_start_halts_the_running_drive_before_it_moves(
    host: Host, kachaka: FakeKachaka
) -> None:
    robot = await navigation(host)
    await robot.execute("start", "c1")
    await asyncio.sleep(0.01)
    await robot.execute("start", "c2")
    assert await robot.completed("c1") == "ABORT"
    await asyncio.sleep(0.01)
    assert kachaka.log[:3] == ["move L1", "cancel", "cancelled L1"]
    assert kachaka.log[-1] == "move L1"
    kachaka.arrive.set()
    assert await robot.completed("c2") == "OK"


async def test_robot_position_reads_the_pose(host: Host, kachaka: FakeKachaka) -> None:
    robot = await host("system_information", GrpcSystemInformation("10.0.0.2:26400"))
    result = await robot.call(
        "rois.query.query", query_type="robot_position", condition=""
    )
    values = {r["name"]: r["value"] for r in result["results"]}
    assert values["position_data"] == '["1.2500,-0.5000,1.5708"]'
    assert values["robot_ref"] == '["kachaka"]'
    status = await robot.call("rois.query.query", query_type="engine_status", condition="")
    assert status["results"][1]["value"] == "READY"
