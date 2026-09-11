# openrois-components-realsense

OpenRoIS components for Intel RealSense cameras, backed by the ROS 2
perception pipeline (`realsense2_camera` + `yolo_person_perception`).
Publishes the pipeline output as the three canonical RoIS camera
components:

| RoIS component | Source topic | Event |
|---|---|---|
| PersonDetection | `/person_detection/count` (`std_msgs/Int32`) | `person_detected` |
| PersonLocalization | `/person_tracks` (`vision_msgs/Detection3DArray`) | `person_localized` |
| PersonIdentification | `/person_tracks` (`vision_msgs/Detection3DArray`) | `person_identified` |

## Coordinate frames

`/person_tracks` positions are in `camera_color_optical_frame`
(+x right, +y down, +z forward). `Ros2PersonLocalization` transforms
them into the target frame (default `camera_link`, REP-103 body
convention) using the static transforms published by the camera driver
on `/tf_static`. Configure via `person_position_frame` /
`person_tracks_frame`.

## Identifier semantics

The IDs published by `Ros2PersonIdentification` are ByteTrack
session-scoped tracking IDs. They reset when the perception pipeline
restarts and may switch under occlusion. They are NOT persistent
personal identities.

## Install

    pip install openrois-components-realsense

For the ROS 2 backend:

    pip install openrois-components-realsense[ros2]

Requires `tf2_ros` and `vision_msgs` (ROS 2 packages, installed with
the ROS 2 desktop environment).

## Usage

See `examples/realsense-adapter` for a complete adapter that registers
the three components and connects them to a gateway.