# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Resource`, the base class of something several components of one adapter share, such as a robot connection or an SDK client. A component records the resources it uses with `self.uses(resource)` in its constructor. The engine opens each one before the first component that uses it connects and closes it after the last one disconnects.
- `self.raise_status(status, message)` and `self.clear_status()` on a component and on a resource, safe from any thread. They report WARNING or ERROR, which `component_status` shows and which reaches clients as `rois.system.notify_error`. A raised ERROR makes the engine refuse the component's commands and queries until it clears.
- `RclpyExecutor`, in `openrois.components.core.ros2`: the one rclpy executor of an adapter, a resource its ROS 2 components share. It initializes rclpy when it opens, unless the process already did, and spins every node handed to it with `add_node` in one background thread. It stops spinning when it closes, after the components have disconnected, and shuts rclpy down only if it initialized it. Where rclpy is missing, the components that use it report ERROR.
- `self.engine_state()`, the status of the engine that hosts the component, for a SystemInformation component's `engine_status`.
- Query and subscribe handlers take the arguments of their message by name, as command handlers do, for example `stream_id` for `get_stream_status`. `emit(event_type, concerning={...}, **values)` names the argument values an event is about, so it reaches only the subscriptions that asked for them.

### Changed

- **Breaking:** a component whose profile includes RoISCommon serves `start`, `stop`, `suspend` and `resume` whether it has handlers for them or not, so it never answers UNSUPPORTED to them. The engine answers them by default, a command without a handler completes OK at once, and a handler adds to the default. A profile without RoISCommon still serves `stop` only with `start`.
- **Breaking:** `EngineBinding` gains `raise_status`, `clear_status` and `engine_status`, and its `emit` takes the argument values the event concerns. `rois_query` and `rois_subscribed` take the arguments of the message.

## [0.1.0a1] - 2026-10-08

### Added

- `Component`, the base class of a RoIS HRI Component, imported from `openrois.components.core`. A component reads its current parameter values as `self.parameters`, converted from their profile types, sends events with `self.emit(event_type, **values)` from any thread, and opens and closes its backend in `connect()` and `disconnect()`.
- `@component(profile)`, which declares the component type with a profile constant such as `NAVIGATION_PROFILE` or a full `HRIComponentProfile`. It checks every handler against the profile when the class is defined.
- `@invoke`, `@query` and `@subscribe`, which mark the commands, queries and events a component implements. The engine serves only those, plus `stop` with `start` and `component_status`.
- Command handlers that run for as long as the command lasts, take the command's arguments by name and return its results by name. `CommandFailed` ends a command with ERROR, ABORT, OUT_OF_RESOURCES or TIMEOUT.
- `@on_set_parameter`, the hook that applies new parameter values to the backend or refuses them.
- `EngineBinding` and the `rois_` methods of `Component`, the side an engine calls to host a component.

[unreleased]: https://github.com/openrois/openrois/compare/components-core-v0.1.0-alpha.1...HEAD
[0.1.0a1]: https://github.com/openrois/openrois/releases/tag/components-core-v0.1.0-alpha.1
