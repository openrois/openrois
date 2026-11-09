# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-10

### Changed

- The first release numbered 0.1.0, in step with OpenRoIS 0.1.0 and `openrois-interfaces` 0.1.0, with the same types, serializer settings and condition builders as 0.1.0-alpha.6.

## [0.1.0-alpha.6] - 2026-11-06

### Added

- `RoISJson.Options`, the serializer settings of the wire format: enumerations as names, and unset fields left out of the message, because the engine refuses a null such as `"arguments": null`.
- `Condition`, which builds the filter text of a `condition` parameter: `Quote`, `Eq`, `Like`, `AllOf`, `ComponentRef`, `ComponentType` and `ComponentTypeUrn`, with the property names `ComponentRefProperty` and `ComponentTypeProperty`.
- `RoISValues.Encode` and `RoISValues.Decode`, the string forms of typed values, with the same type names and rules as `encode_value` and `decode_value` in Python. `NaN`, `Infinity` and `-Infinity` stand bare in a float array. An integer written as a float rounds to the nearest double, and one beyond the range of a double throws `FormatException`.

### Changed

- **Breaking:** the models refuse an unknown field, a missing required field, and null in a field whose C# type is not nullable. Each throws `JsonException`. An optional list or map has a nullable C# type, so an explicit null there reads as absent, where Python and TypeScript refuse it.
- **Breaking:** a model refuses with `JsonException` a null list item, a null map value, and an empty `ExecuteParams.command_unit_list` or `Branch.command_list`.
- Model properties are `{ get; init; }`.
- The package depends on `System.Text.Json` 8.0.6 instead of 9.0.0, the version Unity 6000.6 ships in its class library. Against 9.0, scripts that use these types fail there with CS1705.

### Fixed

- `ICommandUnitSequenceItem` has a JSON converter. `ExecuteParams` no longer writes each item as `{}`, and `ExecuteResult` can be read: an item with `branch_list` is a `ConcurrentCommands` and any other item is a `CommandUnit`.

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

[unreleased]: https://github.com/openrois/openrois/compare/interfaces-v0.1.0...HEAD
[0.1.0]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0
[0.1.0-alpha.6]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.6
[0.1.0-alpha.5]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.5
[0.1.0-alpha.4]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.4
[0.1.0-alpha.3]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.3
[0.1.0-alpha.2]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.1
