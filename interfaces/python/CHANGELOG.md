# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0a2] - 2026-07-02

### Added

- Implement typed component models for `Reaction`.

### Changed

- Bump `requires-python` from `>=3.11` to `>=3.12` (aligns with ROS 2 Jazzy;
  enables PEP 695 `type` statement syntax).
- Add `Programming Language :: Python :: 3.14` classifier.
- Convert all 19 type aliases from bare assignments to PEP 695 `type` statements
  (`hri.py`: 11, `bus.py`: 6, `common.py`: 2). This preserves the named type
  identity that the OMG RoIS specification (IDL/HPP/XSD) deliberately defines
  (`RoIS_Identifier`, `Condition_t`, `DateTime`, `Integer`, etc.).

## [0.1.0a1] - 2026-06-20

### Added

- Implement Pydantic models for all core RoIS types: `ReturnCode`, `Result`, `Parameter`, `Argument`, `CommandUnit`, `ConcurrentCommands`, `CommandUnitSequence` (hri); `ComponentStatus`, `StreamStatus` (common); `CompletedStatus`, `ErrorType`, `CompletedEvent`, `NotifyErrorEvent`, `NotifyEventPayload` (service); `RoISIdentifierType`, `ParameterProfile`, `MessageProfile`, `CommandMessageProfile`, `QueryMessageProfile`, `EventMessageProfile`, `HRIComponentProfile`, `HRIEngineProfileType` (profiles); `BusAdapter` protocol + request/response models (bus).
- Implement typed component models for `PersonDetection`, `Navigation`, and `SystemInformation`.
- Add `export_schema.py` script to generate JSON Schema from Pydantic models into `interfaces/schema/`.
- Add `test_schema_drift.py` to verify committed schemas match Pydantic output (CI guard).
- Cross-check types against `PersonDetection.xml`, `Navigation.xml`, `SystemInformation.xml` and validate against `XML-Profiles.xsd`.

[unreleased]: https://github.com/openrois/openrois/compare/main...HEAD
[0.1.0a2]: https://github.com/openrois/openrois/releases/tag/v0.1.0a2
[0.1.0a1]: https://github.com/openrois/openrois/releases/tag/v0.1.0a1