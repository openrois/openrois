# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- The README gives Unity 6000.0 as the floor and points Unity users to `org.openrois.sdk`, which bundles this assembly.

## [0.1.0-alpha.5] - 2026-10-16

### Added

- `Branch`, `Arguments` on query and event profiles, `ReadOnly` on parameter profiles, and an optional `Name` on engine profiles.
- `ExecuteResult` carries `CommandUnitList`, the sequence with the command ids the engine assigned (OpenRoIS extension).

### Changed

- **Breaking:** `ConcurrentCommands` holds `BranchList`, a list of branches each with an ordered `CommandList`, instead of a flat `CommandList`.
- **Breaking:** a parameter profile without a default has a null `DefaultValue` instead of an empty string.
- **Breaking:** `CommandUnit.CommandId` is optional, since the engine assigns it.

### Removed

- **Breaking:** `UnmodelledMethodPrefixes`. Streaming has no methods of its own.

## [0.1.0-alpha.4] - 2026-10-08

### Changed

- **Breaking:** remove the `OpenRoIS.Interfaces.Contract` and `OpenRoIS.Interfaces.Contract.Models` namespaces. The models of the method catalog are in `OpenRoIS.Interfaces.Catalog`.

## [0.1.0-alpha.3] - 2026-10-08

### Added

- The `OpenRoIS.Interfaces.Catalog` namespace: a params and a result model for each of the 16 `rois.*` methods, `RoISMethods`, `RoISMethodTypes`, `RoISNotifications`, `RoISNotificationTypes`, `RoISCommandTypes` and `JsonRpcErrorCodes`.
- The OpenRoIS extensions `GetProfileResult.ComponentProfiles`, `HRIComponentProfile.Function` with `ComponentFunction`, `NotifyEventParams.Results` and `ProfileChangedParams`.

### Changed

- **Breaking:** remove the `CommandType` enum. `CommandUnit.CommandType` and `CommandRequest.CommandType` are `string`, because a component may define commands of its own. `RoISCommandTypes` lists the standard names.
- **Breaking:** remove `HRIEngineProfileType.ComponentProfiles`. Read the component profiles from `GetProfileResult.ComponentProfiles`.
- **Breaking:** rename `NotifyErrorEvent` to `NotifyErrorParams`, `CompletedEvent` to `CompletedParams` and `NotifyEventPayload` to `NotifyEventParams`. The event notification is `rois.event.notify_event` instead of `rois.event.notify`.
- **Breaking:** rename `IBusAdapter` to `IComponentContract` and `BusAdapterError` to `ComponentContractError` (closes #5). The namespaces `OpenRoIS.Interfaces.Bus` and `OpenRoIS.Interfaces.Bus.Models` are now `OpenRoIS.Interfaces.Contract` and `OpenRoIS.Interfaces.Contract.Models`.

## [0.1.0-alpha.2] - 2026-07-02

### Added

- `sealed class` types for the `Reaction` component models.

### Fixed

- `CommandUnitSequence.CommandUnitList` is `IReadOnlyList<ICommandUnitSequenceItem>?` instead of `IReadOnlyList<object>?`, for compile-time type safety.
- Generated C# types no longer reference missing classes for simple type aliases such as `RoISIdentifier` and `Integer`.

## [0.1.0-alpha.1] - 2026-06-20

### Added

- The `OpenRoIS.Interfaces` package, generated from the JSON Schema: `sealed class` and `enum` types for the core RoIS types and the `PersonDetection`, `Navigation` and `SystemInformation` component models.
- The `IBusAdapter` interface with its error classes.
- `netstandard2.1` target, for Unity 6.3 and later.

[unreleased]: https://github.com/openrois/openrois/compare/interfaces-v0.1.0-alpha.5...HEAD
[0.1.0-alpha.5]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.5
[0.1.0-alpha.4]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.4
[0.1.0-alpha.3]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.3
[0.1.0-alpha.2]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.1
