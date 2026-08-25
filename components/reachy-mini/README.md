# openrois-components-reachy-mini

OpenRoIS components for the [Reachy Mini](https://www.pollen-robotics.com/) robot
by Pollen Robotics. Provides robot-specific implementations of SystemInformation
and other components that translate RoIS messages to Reachy SDK calls.

## Install

    pip install openrois-components-reachy-mini

## Usage

    from openrois_components.reachy_mini import SystemInformation

    class ReachyMiniAdapter(RobotAdapter):
        SystemInformation = SystemInformation