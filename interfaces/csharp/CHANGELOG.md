# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[unreleased]: https://github.com/openrois/openrois/compare/main...HEAD
[0.1.0-alpha.2]: https://github.com/openrois/openrois/releases/tag/v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/openrois/openrois/releases/tag/v0.1.0-alpha.1