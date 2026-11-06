# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0a6] - 2026-11-06

### Added

- `component_ref` and `component_type` in `openrois.interfaces.condition`, which build the condition that selects one component or every component of a type.

### Changed

- **Breaking:** `Integer` is 32 bits, as the IDL `long` it stands for: `delay_time`, `time_limit`, `number` and `CommandMessageProfile.timeout` refuse a value outside -2147483648 to 2147483647, and the XML reader raises `ProfileFormatError` for one.

### Fixed

- `decode_value` reads a float array item too large for a double as signed infinity, as it reads `[1e400]`, and `encode_value` raises `ValueError` for an `int` too large for a double. Both raised `OverflowError`.

## [0.1.0a5] - 2026-10-16

### Added

- `openrois.interfaces.declaration`, to declare your own component type in Python and export it as a profile or as RoIS XML.
- `openrois.interfaces.xmlcodec`, to read and write RoIS XML: component and engine profiles, command unit sequences and command messages.
- A profile constant for each of the 18 standard component types in `openrois.interfaces.components`, with `STANDARD_PROFILES` and `standard_registry()`.
- `openrois.interfaces.type_codes`, whose `python_type()` gives the Python type of a `data_type_ref` code.
- `ExecuteResult.command_unit_list` (OpenRoIS extension), the sequence with the command id the engine assigned to every command.
- `arguments` on query and event profiles, `ParameterProfile.read_only` (OpenRoIS extension) and an optional `HRIEngineProfileType.name`.
- `lxml` is a runtime dependency.

### Changed

- **Breaking:** `CommandUnit.command_id` defaults to empty. The engine a client calls assigns it, and ignores one a client sends.
- **Breaking:** `ConcurrentCommands` holds `branch_list`, a list of `Branch`, each with an ordered `command_list`. A flat `command_list` is still read, as one command per branch.
- **Breaking:** `ParameterProfile.default_value` is `None` when a parameter has no default.
- **Breaking:** remove the `openrois.interfaces.components.rois_common` and `openrois.interfaces.components.speech_synthesis` modules, with the `omg_identifier` and `parameter` helpers. Import every profile constant and URN from `openrois.interfaces.components`.

### Removed

- **Breaking:** `STREAMING_METHOD_PREFIX` and the `unmodelled_method_prefixes` entry of `catalog.json`. Streaming has no methods of its own.

## [0.1.0a4] - 2026-10-08

### Added

- Profile constants for the basic component types the package models, and `ROIS_COMMON_PROFILE`, in `openrois.interfaces.components`, exported to `schema/profiles.json`.
- `openrois.interfaces.values`, whose `encode_value` and `decode_value` convert a typed value to and from the string that travels in `Result.value`, `Parameter.value` and `Argument.value`.

### Changed

- **Breaking:** remove `ComponentStatusT` and `COMPONENT_STATUS_MAP`. A component status travels as its name, for example `READY`.
- **Breaking:** remove the `openrois.interfaces.contract` module and its schemas. Engines and clients exchange the models of the method catalog, and the component contract is part of `openrois-engine`.

## [0.1.0a3] - 2026-10-08

### Added

- `openrois.interfaces.catalog`, the method catalog: a params and a result model for each of the 16 methods, the `SystemIF`, `CommandIF`, `QueryIF` and `EventIF` protocols, `METHODS`, `NOTIFICATIONS` and `JsonRpcErrorCode`, exported to `schema/catalog.json`.
- `openrois.interfaces.condition`, which parses, matches and builds conditions in a subset of CQL2-Text.
- The `EXTENSIONS` registry, which lists every place OpenRoIS adds to RoIS and why.
- The OpenRoIS extensions `GetProfileResult.component_profiles`, `HRIComponentProfile.function` with `ComponentFunction`, `NotifyEventParams.results` and the `rois.system.profile_changed` notification.

### Changed

- **Breaking:** `CommandUnit.command_type` and `CommandRequest.command_type` are plain strings, because a component may define commands of its own. `CommandType` keeps the standard names as constants, and `CommandType.EXECUTE` is removed.
- **Breaking:** remove `HRIEngineProfileType.component_profiles`. Read the component profiles from `GetProfileResult.component_profiles`.
- **Breaking:** rename `NotifyErrorEvent` to `NotifyErrorParams`, `CompletedEvent` to `CompletedParams` and `NotifyEventPayload` to `NotifyEventParams`. The event notification is `rois.event.notify_event` instead of `rois.event.notify`.
- **Breaking:** rename the `openrois.interfaces.bus` module to `openrois.interfaces.contract`, and `BusAdapterError` to `ComponentContractError`.

## [0.1.0a2] - 2026-07-02

### Added

- Typed component models for `Reaction`.

### Changed

- Require Python 3.12 or later.

## [0.1.0a1] - 2026-06-20

### Added

- Pydantic models for the core RoIS types, and typed component models for `PersonDetection`, `Navigation` and `SystemInformation`.
- The `BusAdapter` protocol with its request and response models.
- JSON Schema exported from the models into `interfaces/schema/`.

[unreleased]: https://github.com/openrois/openrois/compare/interfaces-v0.1.0-alpha.6...HEAD
[0.1.0a6]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.6
[0.1.0a5]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.5
[0.1.0a4]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.4
[0.1.0a3]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.3
[0.1.0a2]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.2
[0.1.0a1]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.1
