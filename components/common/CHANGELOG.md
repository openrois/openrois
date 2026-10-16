# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `MockSystemInformation`, a SystemInformation component written with `openrois-components-core` that reports a robot standing still. Its `robot_position` query answers the origin, `0.0,0.0,0.0`, identified by the engine id, and its `engine_status` query answers the status of the engine that hosts it, READY unless WARNING or ERROR is raised on the engine, operable since the component was created. It has no commands and no `component_status`, as `SystemInformation.xml` includes no RoIS_Common profile. Use it to bring an adapter up before the robot is ready, and to test clients.

[unreleased]: https://github.com/openrois/openrois/tree/dev/components/common
