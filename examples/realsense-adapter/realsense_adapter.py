"""RealSense adapter: OpenRoIS adapter for the ROS 2 perception pipeline.

Registers the three canonical RoIS camera components backed by the
ROS 2 perception pipeline (realsense2_camera + yolo_person_perception):

- PersonDetection      <- /person_detection/count
- PersonLocalization   <- /person_tracks (positions, TF-transformed)
- PersonIdentification <- /person_tracks (tracking IDs)

Usage:
    python realsense_adapter.py --config openrois-profile.yaml

The ROS 2 environment must be sourced before running (the adapter
imports rclpy, vision_msgs, and tf2_ros at connect() time).
"""

from __future__ import annotations

import argparse
import logging

from openrois_core import Engine, WsClient, component_config, read_profile
from openrois_components.realsense import (
    Ros2PersonDetection,
    Ros2PersonIdentification,
    Ros2PersonLocalization,
)
from openrois_components_core import meta_from_decorators

logger = logging.getLogger(__name__)


# ─── Component classes to register ───────────────────────────

COMPONENT_CLASSES = [
    Ros2PersonDetection,
    Ros2PersonLocalization,
    Ros2PersonIdentification,
]


def main() -> None:
    """Entry point: load profile, create engine, register components, run."""
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="RealSense OpenRoIS adapter")
    parser.add_argument(
        "--config",
        default="openrois-profile.yaml",
        help="Path to the profile YAML file (default: openrois-profile.yaml)",
    )
    args = parser.parse_args()

    profile = read_profile(args.config)

    engine = Engine(
        engine_id=profile["engine"]["id"],
        platform=profile["engine"].get("platform", ""),
    )

    for cls in COMPONENT_CLASSES:
        meta = meta_from_decorators(cls)
        engine.register_component(
            meta.ref,
            cls(component_config(profile, meta.ref)),
            meta,
        )

    ws_client = WsClient(engine, profile["engine"]["gateway_url"])
    ws_client.run()


if __name__ == "__main__":
    main()