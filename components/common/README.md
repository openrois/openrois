# openrois-components-common

Common reference components and helpers for OpenRoIS adapters. These are
canonical RoIS component implementations that work on any platform. They
are useful for testing, development, and as templates for platform-specific
packages.

## Install

    pip install openrois-components-common

## Usage

    from openrois_components.common.system_information import MockSystemInformation

    class MyAdapter(RobotAdapter):
        SystemInformation = MockSystemInformation