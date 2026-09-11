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
    """Build a robot_position Result list (simplified format).

    Returns x, y, theta as separate float Results. Use
    :func:`robot_position` for the spec-compliant format with
    position_data, robot_ref, and timestamp.

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


def robot_position(
    x: float, y: float, theta: float,
    timestamp: str, robot_ref: list[str],
) -> list[Result]:
    """Build a spec-compliant robot_position Result list.

    Matches the RoIS SystemInformation IDL: position_data (String[]),
    robot_ref (RoISIdentifier[]), timestamp (DateTime).

    Args:
        x: X coordinate in the map frame.
        y: Y coordinate in the map frame.
        theta: Heading angle in radians.
        timestamp: ISO 8601 datetime string.
        robot_ref: List of robot identifiers (engine IDs).

    Returns:
        A list of 3 Result objects (position_data, robot_ref, timestamp).
    """
    return [
        Result(
            name="position_data",
            data_type_ref="String[]",
            value=json.dumps([str(x), str(y), str(theta)], ensure_ascii=False),
        ),
        Result(
            name="robot_ref",
            data_type_ref="RoISIdentifier[]",
            value=json.dumps(robot_ref, ensure_ascii=False),
        ),
        Result(
            name="timestamp",
            data_type_ref="DateTime",
            value=timestamp,
        ),
    ]


def engine_status(
    status: str, operable_time: list[str],
) -> list[Result]:
    """Build a spec-compliant engine_status Result list.

    Matches the RoIS SystemInformation IDL: status (Component_Status),
    operable_time (DateTime[]).

    Args:
        status: Component_Status enum value (READY, BUSY, ERROR, etc.).
        operable_time: List of ISO 8601 datetime strings.

    Returns:
        A list of 2 Result objects (status, operable_time).
    """
    from openrois.interfaces.common import ComponentStatus, COMPONENT_STATUS_MAP

    status_enum = ComponentStatus(status)
    numeric_value = str(COMPONENT_STATUS_MAP[status_enum])

    return [
        Result(
            name="status",
            data_type_ref="Component_Status",
            value=numeric_value,
        ),
        Result(
            name="operable_time",
            data_type_ref="DateTime[]",
            value=json.dumps(operable_time, ensure_ascii=False),
        ),
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
            value=json.dumps(bounding_box, ensure_ascii=False),
        ),
    ]


def status(component_status: str) -> list[Result]:
    """Build a component_status Result list.

    Args:
        component_status: The status string (e.g., "READY", "BUSY", "ERROR").

    Returns:
        A list of 1 Result object (status).
    """
    from openrois.interfaces.common import ComponentStatus, COMPONENT_STATUS_MAP

    status_enum = ComponentStatus(component_status)
    numeric_value = str(COMPONENT_STATUS_MAP[status_enum])

    return [
        Result(
            name="status",
            data_type_ref="Component_Status",
            value=numeric_value,
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


def person_detected(timestamp: str, number: int) -> list[Result]:
    """Build a person_detected event Result list.

    Matches the RoIS PersonDetection IDL: person_detected(timestamp, number).

    Args:
        timestamp: ISO 8601 datetime when the detection was measured.
        number: Number of detected persons in the current observation.

    Returns:
        A list of 2 Result objects (timestamp, number).
    """
    return [
        Result(name="timestamp", data_type_ref="DateTime", value=timestamp),
        Result(name="number", data_type_ref="int", value=str(number)),
    ]


def person_localized(
    timestamp: str,
    positions: list[dict[str, object]],
) -> list[Result]:
    """Build a person_localized event Result list.

    Matches the RoIS PersonLocalization IDL:
    person_localized(timestamp, number, positions).

    Each position dict must have: id (str), x (float), y (float),
    z (float) — in the robot body frame (REP-103: +x forward, +y left,
    +z up), meters.

    Args:
        timestamp: ISO 8601 datetime when the positions were measured.
        positions: List of per-person position dicts.

    Returns:
        A list of 3 Result objects (timestamp, number, positions).
    """
    return [
        Result(name="timestamp", data_type_ref="DateTime", value=timestamp),
        Result(name="number", data_type_ref="int", value=str(len(positions))),
        Result(
            name="positions",
            data_type_ref="PersonPosition[]",
            value=json.dumps(positions, ensure_ascii=False),
        ),
    ]


def person_identified(
    timestamp: str,
    identifiers: list[dict[str, object]],
) -> list[Result]:
    """Build a person_identified event Result list.

    Matches the RoIS PersonIdentification IDL:
    person_identified(timestamp, number, identifiers).

    Each identifier dict must have: id (str), name (str, optional).
    The IDs are session-scoped tracking IDs, not persistent personal
    identities.

    Args:
        timestamp: ISO 8601 datetime when the identification was measured.
        identifiers: List of per-person identifier dicts.

    Returns:
        A list of 3 Result objects (timestamp, number, identifiers).
    """
    return [
        Result(name="timestamp", data_type_ref="DateTime", value=timestamp),
        Result(name="number", data_type_ref="int", value=str(len(identifiers))),
        Result(
            name="identifiers",
            data_type_ref="PersonIdentifier[]",
            value=json.dumps(identifiers, ensure_ascii=False),
        ),
    ]
