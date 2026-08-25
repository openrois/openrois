# openrois-components-kachaka

OpenRoIS components for the [Kachaka](https://kachaka.life/) robot.
Provides robot-specific implementations of canonical RoIS components
that translate RoIS messages to Kachaka gRPC or ROS 2 calls.

## Install

    pip install openrois-components-kachaka

For the gRPC API backend:

    pip install openrois-components-kachaka[api]

For the ROS 2 backend:

    pip install openrois-components-kachaka[ros2]

## Usage

    from openrois_components.kachaka import Navigation

    class KachakaApiAdapter(RobotAdapter):
        Navigation = Navigation