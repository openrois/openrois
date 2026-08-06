"""Tests for the results helper functions."""

from __future__ import annotations

import json

from openrois.interfaces.hri import Result

from openrois.sdk import results


def test_position():
    """position() returns 3 Results with x, y, theta."""
    result = results.position(x=3.2, y=1.8, theta=0.5)
    assert len(result) == 3
    assert result[0].name == "x"
    assert result[0].value == "3.2"
    assert result[1].name == "y"
    assert result[1].value == "1.8"
    assert result[2].name == "theta"
    assert result[2].value == "0.5"


def test_detection():
    """detection() returns 3 Results with object_id, class, bbox."""
    bbox = [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4], [0.1, 0.4]]
    result = results.detection(
        object_id="0",
        object_class="person",
        bounding_box=bbox,
    )
    assert len(result) == 3
    assert result[0].name == "object_id"
    assert result[0].value == "0"
    assert result[1].name == "object_class"
    assert result[1].value == "person"
    assert result[2].name == "bounding_box"
    parsed = json.loads(result[2].value)
    assert parsed == bbox


def test_status():
    """status() returns 1 Result with the status string."""
    result = results.status("BUSY")
    assert len(result) == 1
    assert result[0].name == "component_status"
    assert result[0].value == "BUSY"


def test_waypoints():
    """waypoints() returns one Result per location."""
    locations = [
        {"id": "desk", "name": "desk", "x": 2.0, "y": 1.5, "theta": 0.0},
        {"id": "kitchen", "name": "kitchen", "x": 5.0, "y": 3.0, "theta": 1.57},
    ]
    result = results.waypoints(locations)
    assert len(result) == 2
    assert result[0].name == "desk"
    assert result[1].name == "kitchen"
    parsed = json.loads(result[0].value)
    assert parsed["id"] == "desk"
    assert parsed["x"] == 2.0


def test_reached_target():
    """reached_target() returns 2 Results with target and is_final_target."""
    result = results.reached_target(target="desk", is_final_target=True)
    assert len(result) == 2
    assert result[0].name == "target"
    assert result[0].value == "desk"
    assert result[1].name == "is_final_target"
    assert result[1].value == "true"


def test_manipulation_complete():
    """manipulation_complete() returns 2 Results with success and detail."""
    result = results.manipulation_complete(success=False, detail="gripper jam")
    assert len(result) == 2
    assert result[0].name == "success"
    assert result[0].value == "false"
    assert result[1].name == "detail"
    assert result[1].value == "gripper jam"


def test_battery_level():
    """battery_level() returns 1 Result with percentage."""
    result = results.battery_level(percentage=85.5)
    assert len(result) == 1
    assert result[0].name == "percentage"
    assert result[0].value == "85.5"


def test_gripper_state():
    """gripper_state() returns 1 Result with the state."""
    result = results.gripper_state("open")
    assert len(result) == 1
    assert result[0].name == "gripper_state"
    assert result[0].value == "open"


def test_current_grasped_object():
    """current_grasped_object() returns 1 Result with object_id."""
    result = results.current_grasped_object("obj_42")
    assert len(result) == 1
    assert result[0].name == "object_id"
    assert result[0].value == "obj_42"


def test_all_helpers_return_result_models():
    """All helpers return openrois.interfaces.hri.Result instances."""
    result = results.position(x=1.0, y=2.0, theta=0.0)
    assert all(isinstance(r, Result) for r in result)
