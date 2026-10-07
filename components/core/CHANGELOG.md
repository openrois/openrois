# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Component`, the base class of a RoIS HRI Component, imported from `openrois.components.core`. A component reads its current parameter values as `self.parameters`, converted from their profile types, sends events with `self.emit(event_type, **values)` from any thread, and opens and closes its backend in `connect()` and `disconnect()`.
- `@component(profile)`, which declares the component type with a profile constant such as `NAVIGATION_PROFILE` or a full `HRIComponentProfile`. It checks every handler against the profile when the class is defined.
- `@invoke`, `@query` and `@subscribe`, which mark the commands, queries and events a component implements. The engine serves only those, plus `stop` with `start` and `component_status`.
- Command handlers that run for as long as the command lasts, take the command's arguments by name and return its results by name. `CommandFailed` ends a command with ERROR, ABORT, OUT_OF_RESOURCES or TIMEOUT.
- `@on_set_parameter`, the hook that applies new parameter values to the backend or refuses them.
- `EngineBinding` and the `rois_` methods of `Component`, the side an engine calls to host a component.
