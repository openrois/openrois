# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0-alpha.6] - 2026-11-06

### Added

- `encodeValue` and `decodeValue`, with `RoISValue` and `RoISValueError`, in the package root and the `./values` subpath export. They write and read the string form of a typed value, the same text as `encode_value` and `decode_value` in the Python package.
- `./components` exports the profile constants of all 18 standard component types, and the `Reaction` schemas and types.

### Changed

- **Breaking:** an integer field is 32 bits, as the IDL `long` it stands for: `delay_time`, `time_limit`, `number` and `timeout` refuse a value outside -2147483648 to 2147483647.
- **Breaking:** `ExecuteParamsSchema` refuses an empty `command_unit_list` and `BranchSchema` refuses an empty `command_list`, as the engine does.

### Fixed

- The package loads in Node.js, which failed with `ERR_MODULE_NOT_FOUND`: every relative import carries its `.js` extension.
- `require` works from Node.js 22.12, which failed with `ERR_PACKAGE_PATH_NOT_EXPORTED`: every `exports` entry has `types` first, then a `default` condition.
- Under `moduleResolution: nodenext` every type resolves, so a field that does not exist is a compile error. With `skipLibCheck`, a type that crossed modules used to become `any`, for example the params of `rois.command.completed` in `RoISNotificationMap`.

## [0.1.0-alpha.5] - 2026-10-16

### Added

- The profile constants of all 18 standard component types in `./components`.
- `BranchSchema`, `arguments` on query and event profiles, `read_only` on parameter profiles, and an optional `name` on engine profiles.
- `ExecuteResultSchema` carries `command_unit_list`, the sequence with the command ids the engine assigned (OpenRoIS extension).

### Changed

- **Breaking:** `ConcurrentCommandsSchema` takes `branch_list`, a list of branches each with an ordered `command_list`, instead of a flat `command_list`.
- **Breaking:** a parameter profile without a default has `default_value: null` instead of `""`.
- **Breaking:** `command_id` is optional on a command unit, since the engine assigns it.

### Removed

- **Breaking:** `UnmodelledMethodPrefixes`. Streaming has no methods of its own.

## [0.1.0-alpha.4] - 2026-10-08

### Added

- The profile constants of the basic components in `./components`, with `ROIS_COMMON_PROFILE`.

### Changed

- **Breaking:** remove the `ComponentStatusT` type. A component status travels as its name, for example `READY`.
- **Breaking:** remove the `./contract` subpath export and its names from the package root. Clients and engines exchange the params and result schemas of `./catalog`.

## [0.1.0-alpha.3] - 2026-10-08

### Added

- The `./catalog` subpath export: a params and a result schema for each of the 16 `rois.*` methods, `RoISMethods`, `RoISMethodSchemas`, `RoISNotifications`, `RoISNotificationSchemas`, `RoISCommandTypes` and `JsonRpcErrorCode`.
- The `./condition` subpath export, which reads, matches and builds conditions in the CQL2-Text subset.
- The OpenRoIS extensions `GetProfileResult.component_profiles`, `HRIComponentProfile.function` with `ComponentFunctionSchema`, `NotifyEventParams.results` and `ProfileChangedParamsSchema`.

### Changed

- **Breaking:** `CommandType` is a `string` alias, and `CommandTypeSchema` is removed, because a component may define commands of its own. `RoISCommandTypes` lists the standard names.
- **Breaking:** remove `component_profiles` from `HRIEngineProfileType`. Read the component profiles from `GetProfileResult.component_profiles`.
- **Breaking:** rename `NotifyErrorEventSchema` to `NotifyErrorParamsSchema`, `CompletedEventSchema` to `CompletedParamsSchema` and `NotifyEventPayloadSchema` to `NotifyEventParamsSchema`, with their types. The event notification is `rois.event.notify_event` instead of `rois.event.notify`.
- **Breaking:** `ArgumentListSchema` is no longer exported. `ArgumentList` remains as a type alias.
- **Breaking:** rename `BusAdapter` to `ComponentContract` and `BusAdapterError` to `ComponentContractError` (closes #5). The `./bus` subpath export is now `./contract`.

## [0.1.0-alpha.2] - 2026-07-02

### Added

- Zod schemas and inferred types for the `Reaction` component models.

### Fixed

- Generated zod schemas no longer reference missing schema variables for simple type aliases such as `RoISIdentifier` and `Integer`.

## [0.1.0-alpha.1] - 2026-06-20

### Added

- The `@openrois/interfaces` ESM package, generated from the JSON Schema: zod schemas and inferred types for the core RoIS types and the `PersonDetection`, `Navigation` and `SystemInformation` component models.
- The `BusAdapter` interface with its error classes.

[unreleased]: https://github.com/openrois/openrois/compare/interfaces-v0.1.0-alpha.6...HEAD
[0.1.0-alpha.6]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.6
[0.1.0-alpha.5]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.5
[0.1.0-alpha.4]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.4
[0.1.0-alpha.3]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.3
[0.1.0-alpha.2]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.1
