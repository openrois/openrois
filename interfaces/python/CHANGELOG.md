# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add a profile constant for each basic component type the package models: `NAVIGATION_PROFILE`, `PERSON_DETECTION_PROFILE`, `REACTION_PROFILE` and `SYSTEM_INFORMATION_PROFILE` in `openrois.interfaces.components`, and `ROIS_COMMON_PROFILE` with `ROIS_COMMON_URN` for the RoIS_Common profile they include. Each constant is the full profile of its type: the XML profile with the RoIS_Common messages listed first, and the RoSO function. A component declares the constant of its type and implements a part of it.
- Export the profile constants to `schema/profiles.json` with `profiles_document()`, for the TypeScript generator.
- Cross-check every profile constant against its XML profile and `OWL.ttl` when the normative files are available.
- Add the `openrois.interfaces.values` module: `encode_value` and `decode_value` write a typed value as the string that travels in `Result.value`, `Parameter.value` and `Argument.value`, and read it back, by its `data_type_ref`. Numbers are decimal, booleans `true` or `false`, a `Component_Status` its name, and an array type a JSON array.

### Changed

- **Breaking:** remove `ComponentStatusT` and `COMPONENT_STATUS_MAP`. A component status travels as its name, for example `READY`, as the XML profiles type it.

## [0.1.0a3] - 2026-10-08

### Added

- Add the `openrois.interfaces.catalog` module, the service-side method catalog. It has a params and a result model for each of the 16 methods of SystemIF, CommandIF, QueryIF and EventIF, named after the IDL parameters, the `SystemIF`, `CommandIF`, `QueryIF` and `EventIF` protocols, the `METHODS` table and `JsonRpcErrorCode`. `rois.stream.*` is not modelled.
- Export the method table to `schema/catalog.json`, which the TypeScript and C# generators read.
- Cross-check every catalog model against `RoIS_HRI.idl` when the normative files are available.
- Add the `openrois.interfaces.condition` module. Every `condition` is a string in a subset of CQL2-Text (`=`, `LIKE` and `AND`) over the `component_ref` and `component_type` properties. The module parses and matches conditions and builds them with correct quoting.
- Add the `NOTIFICATIONS` table: `rois.system.notify_error`, `rois.command.completed` and `rois.event.notify_event` for the ServiceApplicationBase operations, and `rois.system.profile_changed` (`ProfileChangedParams`), which an engine sends when its profile changes. `catalog.json` lists the notifications and the standard command names.
- Add the `EXTENSIONS` registry, which lists every place OpenRoIS adds to RoIS and why. The IDL and XSD cross-checks allow exactly these additions.
- Add `GetProfileResult.component_profiles`, the profile of every component the engine profile lists, keyed by fully qualified ref (OpenRoIS extension).
- Add `HRIComponentProfile.function` and the `ComponentFunction` enum (`actuation`, `sensing`, `function`), the RoSO function class of a component (OpenRoIS extension).
- Add `NotifyEventParams.results`, the event payload (OpenRoIS extension).
- Cross-check the notification params against `RoIS_Service.idl`, and the engine and component profile models against `XML-Profiles.xsd` field by field.

### Changed

- Describe every `condition` field as CQL2-Text instead of an ISO 19143 expression.
- **Breaking:** `CommandUnit.command_type` and `CommandRequest.command_type` are plain strings, as in the IDL and the XSD, because a component may define commands of its own. `CommandType` keeps the standard names (`start`, `stop`, `suspend`, `resume`, `set_parameter`) as constants. `CommandType.EXECUTE` is removed: `execute` is a CommandIF method, not a component command.
- **Breaking:** remove `HRIEngineProfileType.component_profiles`. The engine profile now matches the XSD and names its components by ref in `component_ids`, which lists every component reachable through the engine. The component profiles moved to `GetProfileResult.component_profiles`.
- **Breaking:** rename the service models after the notification that carries them: `NotifyErrorEvent` to `NotifyErrorParams`, `CompletedEvent` to `CompletedParams` and `NotifyEventPayload` to `NotifyEventParams`. The event notification is `rois.event.notify_event`, after the ServiceApplicationBase operation, instead of `rois.event.notify`.
- **Breaking:** rename the `openrois.interfaces.bus` module to `openrois.interfaces.contract`, and `BusAdapterError` to `ComponentContractError`. The JSON Schema manifest module is now `contract`.

### Fixed

- Regenerate the contract schemas, whose descriptions still named `BusAdapter`.
- Skip the normative cross-check tests unless `OPENROIS_NORMATIVE_DIR` points to the OMG files.
- Set `mypy_path` and `explicit_package_bases` in `pyproject.toml`, so `mypy src/` resolves the `openrois` namespace package without extra flags.

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

[unreleased]: https://github.com/openrois/openrois/compare/interfaces-v0.1.0-alpha.3...HEAD
[0.1.0a3]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.3
[0.1.0a2]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.2
[0.1.0a1]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.1
