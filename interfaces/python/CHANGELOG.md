# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add the `openrois.interfaces.catalog` module, the service-side method catalog. It has a params and a result model for each of the 16 methods of SystemIF, CommandIF, QueryIF and EventIF, named after the IDL parameters, the `SystemIF`, `CommandIF`, `QueryIF` and `EventIF` protocols, the `METHODS` table and `JsonRpcErrorCode`. `rois.stream.*` is not modelled.
- Export the method table to `schema/catalog.json`, which the TypeScript and C# generators read.
- Cross-check every catalog model against `RoIS_HRI.idl` when the normative files are available.

### Changed

- **Breaking:** rename the `openrois.interfaces.bus` module to `openrois.interfaces.contract`, and `BusAdapterError` to `ComponentContractError`. The JSON Schema manifest module is now `contract`.

### Fixed

- Regenerate the contract schemas, whose descriptions still named `BusAdapter`.
- Skip the normative cross-check tests unless `OPENROIS_NORMATIVE_DIR` points to the OMG files.

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