# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-10

### Changed

- The first release numbered 0.1.0, in step with OpenRoIS 0.1.0. `openrois-components-core` 0.1.0 requires `openrois-interfaces` 0.1.0 or later, before 0.2, and runs in `openrois-engine` 0.1.0.

## [0.1.0a2] - 2026-11-09

### Changed

- **Breaking:** components mark their RoIS messages with decorators named after the kind of message: `@command(command_type)`, `@query(query_type)` and `@event(event_type)`. Code that uses `@invoke` or `@subscribe` uses `@command` or `@event`.
- **Breaking:** a component applies new parameter values with `@command("set_parameter")`, whose handler takes the new values as its one argument. The engine checks the values against the profile first, and stores them only if the handler does not raise. Code that uses `@on_set_parameter` uses `@command("set_parameter")`.

## [0.1.0a1] - 2026-11-05

### Added

- `Component`, the base class of a RoIS HRI Component, with its parameters, `emit` from any thread, and `connect()` and `disconnect()` for its backend.
- `@component(profile)`, which declares the component type and checks every handler against the profile when the class is defined.
- `@invoke`, `@query` and `@subscribe`, whose handlers take arguments and return results by name. `CommandFailed` ends a command with the status it names.
- The RoIS_Common commands, which the engine answers by default. A handler adds to the default.
- `@on_set_parameter`, the hook that applies new parameter values or refuses them.
- `Resource`, something several components of one adapter share, opened and closed by the engine.
- `raise_status` and `clear_status` on a component and on a resource, safe from any thread.
- `RclpyExecutor`, in `openrois.components.core.ros2`, the one rclpy executor of an adapter.
- `self.engine_state()`, the status of the engine that hosts the component.
- `EngineBinding` and the `rois_` methods of `Component`, the side an engine calls to host a component.
- Type information for every public name (`py.typed`).
- `openrois-interfaces` 0.1.0a5 or later is required, because the SDK reads the `arguments` of query and event profiles, which that release introduced.

[unreleased]: https://github.com/openrois/openrois/compare/components-core-v0.1.0...HEAD
[0.1.0]: https://github.com/openrois/openrois/releases/tag/components-core-v0.1.0
[0.1.0a2]: https://github.com/openrois/openrois/releases/tag/components-core-v0.1.0-alpha.2
[0.1.0a1]: https://github.com/openrois/openrois/releases/tag/components-core-v0.1.0-alpha.1
