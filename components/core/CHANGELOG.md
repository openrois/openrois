# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Component`, the base class of a RoIS HRI Component, imported from `openrois.components.core`. A component reads its current parameter values as `self.parameters`, converted from their profile types, sends events with `self.emit(event_type, **values)` from any thread, and opens and closes its own backend in `connect()` and `disconnect()`.
- `@component(profile)`, which declares the component type with a profile constant such as `NAVIGATION_PROFILE` or a full `HRIComponentProfile`. It checks every handler against the profile when the class is defined.
- `@invoke`, `@query` and `@subscribe`, which mark the commands, queries and events a component implements. The engine serves those, `component_status`, and the four RoIS_Common commands.
- The RoIS_Common commands without handlers. A component whose profile includes RoISCommon serves `start`, `stop`, `suspend` and `resume` whether it has handlers for them or not, so it never answers UNSUPPORTED to them. The engine answers them by default, a command without a handler completes OK at once, and a handler adds to the default. A profile without RoISCommon serves `stop` only with `start`.
- Command handlers that run for as long as the command lasts, take the command's arguments by name and return its results by name. `CommandFailed` ends a command with ERROR, ABORT, OUT_OF_RESOURCES or TIMEOUT.
- Query and subscribe handlers that take the arguments of their message by name, as command handlers do, for example `stream_id` for `get_stream_status`. `emit(event_type, concerning={...}, **values)` names the argument values an event is about, so it reaches only the subscriptions that asked for them.
- `@on_set_parameter`, the hook that applies new parameter values to the backend or refuses them. A refusal answers the client BAD_PARAMETER, and the old values stay.
- `Resource`, the base class of something several components of one adapter share, such as a robot connection or an SDK client. The adapter creates it, and a component records it with `self.uses(resource)` in its constructor. The engine opens each one before the first component that uses it connects and closes it after the last one disconnects.
- `self.raise_status(status, message)` and `self.clear_status()` on a component and on a resource, safe from any thread. They report WARNING or ERROR, which `component_status` shows and which reaches clients as `rois.system.notify_error`. A raised ERROR makes the engine refuse the component's commands and queries until it clears.
- `RclpyExecutor`, in `openrois.components.core.ros2`: the one rclpy executor of an adapter, a resource its ROS 2 components share. It initializes rclpy when it opens, unless the process already did, and spins every node handed to it with `add_node` in one background thread. It stops spinning when it closes, after the components have disconnected, and shuts rclpy down only if it initialized it. Where rclpy is missing, the components that use it report ERROR.
- `self.engine_state()`, the status of the engine that hosts the component, for a SystemInformation component's `engine_status`.
- `EngineBinding` and the `rois_` methods of `Component`, the side an engine calls to host a component.

[unreleased]: https://github.com/openrois/openrois/tree/dev/components/core
