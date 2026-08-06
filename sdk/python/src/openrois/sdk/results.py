"""Helper functions for building common Result lists.

These helpers produce openrois.interfaces.hri.Result models with the correct
field names and JSON-encoded values. Use them in @query and @subscribe
handlers to avoid manual Result construction.

Example::

    @query("robot_position")
    async def robot_position(self):
        return results.position(x=3.2, y=1.8, theta=0.5)
"""

from __future__ import annotations

import json

from openrois.interfaces.hri import Result


def position(x: float, y: float, theta: float) -> list[Result]:
    """Build a robot_position Result list.

    Args:
        x: X coordinate in the map frame.
        y: Y coordinate in the map frame.
        theta: Heading angle in radians.

    Returns:
        A list of 3 Result objects (x, y, theta).
    """
    return [
        Result(name="x", data_type_ref="float", value=str(x)),
        Result(name="y", data_type_ref="float", value=str(y)),
        Result(name="theta", data_type_ref="float", value=str(theta)),
    ]


def detection(
    object_id: str,
    object_class: str,
    bounding_box: list[list[float]],
) -> list[Result]:
    """Build an object_detected or list_objects Result list.

    Args:
        object_id: Unique identifier for the detected object.
        object_class: Semantic class label (e.g., "person", "cup").
        bounding_box: Polygon coordinates as [[x1,y1], [x2,y2], ...].

    Returns:
        A list of 3 Result objects (object_id, object_class, bounding_box).
    """
    return [
        Result(name="object_id", data_type_ref="string", value=object_id),
        Result(name="object_class", data_type_ref="string", value=object_class),
        Result(
            name="bounding_box",
            data_type_ref="polygon",
            value=json.dumps(bounding_box),
        ),
    ]


def status(component_status: str) -> list[Result]:
    """Build a component_status Result list.

    Args:
        component_status: The status string (e.g., "READY", "BUSY", "ERROR").

    Returns:
        A list of 1 Result object (component_status).
    """
    return [
        Result(
            name="component_status",
            data_type_ref="string",
            value=component_status,
        ),
    ]


def waypoints(locations: list[dict[str, object]]) -> list[Result]:
    """Build a waypoints Result list from location dicts.

    Each location dict should have: id, name, x, y, theta (optional).

    Args:
        locations: List of location dicts.

    Returns:
        A list of Result objects, one per waypoint.
    """
    return [
        Result(
            name=str(loc["name"]),
            data_type_ref="waypoint",
            value=json.dumps(loc, ensure_ascii=False),
        )
        for loc in locations
    ]


def reached_target(target: str, is_final_target: bool) -> list[Result]:
    """Build a reached_target event Result list.

    Args:
        target: The reached target destination.
        is_final_target: Whether this is the final destination point.

    Returns:
        A list of 2 Result objects (target, is_final_target).
    """
    return [
        Result(name="target", data_type_ref="string", value=target),
        Result(
            name="is_final_target",
            data_type_ref="bool",
            value=str(is_final_target).lower(),
        ),
    ]


def manipulation_complete(success: bool, detail: str = "") -> list[Result]:
    """Build a manipulation_complete event Result list.

    Args:
        success: Whether the manipulation succeeded.
        detail: Optional detail message.

    Returns:
        A list of 2 Result objects (success, detail).
    """
    return [
        Result(name="success", data_type_ref="bool", value=str(success).lower()),
        Result(name="detail", data_type_ref="string", value=detail),
    ]


def battery_level(percentage: float) -> list[Result]:
    """Build a battery_level Result list.

    Args:
        percentage: Battery percentage (0.0 to 100.0).

    Returns:
        A list of 1 Result object (percentage).
    """
    return [
        Result(name="percentage", data_type_ref="float", value=str(percentage)),
    ]


def gripper_state(state: str) -> list[Result]:
    """Build a gripper_state Result list.

    Args:
        state: The gripper state (e.g., "open", "closed").

    Returns:
        A list of 1 Result object (gripper_state).
    """
    return [
        Result(name="gripper_state", data_type_ref="string", value=state),
    ]


def current_grasped_object(object_id: str) -> list[Result]:
    """Build a current_grasped_object Result list.

    Args:
        object_id: The object ID currently grasped, or empty string.

    Returns:
        A list of 1 Result object (object_id).
    """
    return [
        Result(name="object_id", data_type_ref="string", value=object_id),
    ]
