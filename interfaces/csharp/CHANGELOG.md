# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Breaking:** remove the `OpenRoIS.Interfaces.Contract` and `OpenRoIS.Interfaces.Contract.Models` namespaces: `IComponentContract`, its request and response models, `EventEnvelope`, `EventSink` and the error classes. Every source file is generated, and the models of the method catalog are in `OpenRoIS.Interfaces.Catalog`.

## [0.1.0-alpha.3] - 2026-10-08

### Added

- Add the `OpenRoIS.Interfaces.Catalog` namespace with a params and a result model for each of the 16 `rois.*` methods, `RoISMethods`, `RoISMethodTypes` and `JsonRpcErrorCodes`, generated from `schema/catalog.json`.
- Add `RoISNotifications` and `RoISNotificationTypes` for `rois.system.notify_error`, `rois.command.completed`, `rois.event.notify_event` and `rois.system.profile_changed`, and `RoISCommandTypes`, the standard command names.
- Add `ProfileChangedParams`, `GetProfileResult.ComponentProfiles` (component profiles keyed by fully qualified ref), `HRIComponentProfile.Function` with the `ComponentFunction` enum, and `NotifyEventParams.Results`. All three properties are OpenRoIS extensions.
- The generator writes a JSON Schema map (`additionalProperties` with a schema) as `IReadOnlyDictionary<string, T>`.

### Changed

- Describe every `condition` property as the OpenRoIS subset of CQL2-Text.
- The generator resolves the namespace of a type defined in another module from the manifest, instead of a hard-coded list.
- **Breaking:** remove the `CommandType` enum. `CommandUnit.CommandType` and `CommandRequest.CommandType` are `string`, as in the IDL and the XSD, because a component may define commands of its own. `RoISCommandTypes` lists the standard names.
- **Breaking:** remove `HRIEngineProfileType.ComponentProfiles`. The engine profile now matches the XSD. Read the component profiles from `GetProfileResult.ComponentProfiles`.
- **Breaking:** rename `NotifyErrorEvent` to `NotifyErrorParams`, `CompletedEvent` to `CompletedParams` and `NotifyEventPayload` to `NotifyEventParams`. The event notification is `rois.event.notify_event` instead of `rois.event.notify`.
- **Breaking:** rename `IBusAdapter` to `IComponentContract` and `BusAdapterError` to `ComponentContractError` (closes #5). The namespaces `OpenRoIS.Interfaces.Bus` and `OpenRoIS.Interfaces.Bus.Models` are now `OpenRoIS.Interfaces.Contract` and `OpenRoIS.Interfaces.Contract.Models`, and the generated models moved to `Generated/ContractModels.cs`.

## [0.1.0-alpha.2] - 2026-07-02

### Added

- Emit `sealed class` types for `Reaction` component models.

### Fixed

- Fix `CommandUnitSequence.CommandUnitList` type from `IReadOnlyList<object>?`
  to `IReadOnlyList<ICommandUnitSequenceItem>?` for compile-time type safety.
- Fix generated C# types that referenced non-existent classes for simple type
  aliases (`RoISIdentifier`, `Integer`, etc.). These are now resolved inline to
  their C# type equivalents.

## [0.1.0-alpha.1] - 2026-06-20

### Added

- Generate `OpenRoIS.Interfaces` C# package from 38 JSON Schema files in `interfaces/schema/`.
- Emit C# `sealed class` types for all core HRI, Common, Service, Profile, Bus, and component models (`PersonDetection`, `Navigation`, `SystemInformation`).
- Emit C# `enum` types for `ReturnCode`, `ComponentStatus`, `StreamStatus`, `CompletedStatus`, `ErrorType`.
- Hand-write `IBusAdapter` interface, `EventSink` delegate, `BusAdapterError` and `ComponentNotFoundError` exception classes.
- Target `netstandard2.1` for Unity 6.3+ (Mono) through Unity 6.8 (CoreCLR) compatibility.
- Custom generator (`scripts/Generator`) handling `$defs`, `$ref`, `anyOf` unions, recursive types, enums, and defaults.

[unreleased]: https://github.com/openrois/openrois/compare/interfaces-v0.1.0-alpha.3...HEAD
[0.1.0-alpha.3]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.3
[0.1.0-alpha.2]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.1
