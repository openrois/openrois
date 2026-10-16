# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Declare your own component type in Python with `openrois.interfaces.declaration`. A `ComponentDeclaration` names the identifier, the name, the RoSO function (`sensing`, `actuation` or `function`), the commands, queries, events and parameters, and the sub-profiles (RoIS_Common unless you say otherwise). `profile()` gives the `HRIComponentProfile` a component class declares, and `to_xml()` gives the RoIS XML profile. A query and an event may share a name, and any type code is accepted, so the Annex C examples such as the wheelchair and the grammar-based speech recognizer can be written as they are.
- Read and write RoIS XML with `openrois.interfaces.xmlcodec`: component profiles (`read_component_profile`, `write_component_profile`), engine profiles (`read_engine_profile`, `write_engine_profile`, and `write_engine_bundle` for an engine with one document per component it names), command unit sequences (`read_command_unit_sequence`, `write_command_unit_sequence`) and single command messages (`read_command_message`). A `ProfileRegistry` resolves SubComponentProfile references. The reader needs no network and loads no external entities. It reads the RoIS namespace as published (`http://www.omg.org/spec/RoIS/20240801`) and also as `http://www.omg.org/spec/RoIS/20250801`, and the writer emits the first. It reads concurrent commands in every form the specification shows: the Annex B.1 `branch_list`, the flat `command_list` of the XSD, and a `command_list` that holds branches as formal Table 8-15 names it.
- All 18 standard component types now have a profile constant in `openrois.interfaces.components`, generated from the OMG files by `tools/generate_profiles.py`. New: `AUDIO_STREAMING_PROFILE`, `VIDEO_STREAMING_PROFILE`, `FACE_DETECTION_PROFILE`, `FACE_LOCALIZATION_PROFILE`, `FOLLOW_PROFILE`, `GESTURE_RECOGNITION_PROFILE`, `MOVE_PROFILE`, `PERSON_IDENTIFICATION_PROFILE`, `PERSON_LOCALIZATION_PROFILE`, `SOUND_DETECTION_PROFILE`, `SOUND_LOCALIZATION_PROFILE` and `SPEECH_RECOGNITION_PROFILE`, each with its `_URN`. `SPEECH_SYNTHESIS_PROFILE` and `SPEECH_SYNTHESIS_URN` are added too. `STANDARD_PROFILES` lists them all and `standard_registry()` returns a registry holding them. `profiles.json` lists all 18.
- Add `openrois.interfaces.type_codes`: `python_type()` gives the Python type of a `data_type_ref` code (`string` and `String` are `str`, `int[]` is `list[int]`, `Component_Status` is `ComponentStatus`), and an unknown code maps to `Any`.
- Query and event profiles carry `arguments`. The streaming profiles use them for `stream_id`.
- Add `ParameterProfile.read_only` (OpenRoIS extension). It is set on the parameters the specification lists only under get_parameter: `available_encodings` and `available_transports` of the streaming types, and `recognizable_gestures` of GestureRecognition.
- Add `HRIEngineProfileType.name`, the gml:name of an engine, optional.
- `lxml` is now a runtime dependency.

### Changed

- **Breaking:** `ConcurrentCommands` holds `branch_list`, a list of `Branch`, each with an ordered `command_list`. The branches run in parallel and each branch runs its commands in order. A flat `command_list` is still read, as one command per branch, but the model and its JSON Schema only write `branch_list`.
- **Breaking:** `ParameterProfile.default_value` is `None` when a parameter has no default. An empty `default_value` reads as `None`, because the XML profiles write `default_value=""` on parameters that have none.
- **Breaking:** remove the `openrois.interfaces.components.rois_common` and `openrois.interfaces.components.speech_synthesis` modules, with the `omg_identifier` and `parameter` helpers. Import every profile constant and URN from `openrois.interfaces.components`. The typed message models stay where they were.

## [0.1.0a4] - 2026-10-08

### Added

- Add a profile constant for each basic component type the package models: `NAVIGATION_PROFILE`, `PERSON_DETECTION_PROFILE`, `REACTION_PROFILE` and `SYSTEM_INFORMATION_PROFILE` in `openrois.interfaces.components`, and `ROIS_COMMON_PROFILE` with `ROIS_COMMON_URN` for the RoIS_Common profile they include. Each constant is the full profile of its type: the XML profile with the RoIS_Common messages listed first, and the RoSO function. A component declares the constant of its type and implements a part of it.
- Export the profile constants to `schema/profiles.json` with `profiles_document()`, for the TypeScript generator.
- Cross-check every profile constant against its XML profile and `OWL.ttl` when the normative files are available.
- Add the `openrois.interfaces.values` module: `encode_value` and `decode_value` write a typed value as the string that travels in `Result.value`, `Parameter.value` and `Argument.value`, and read it back, by its `data_type_ref`. Numbers are decimal, booleans `true` or `false`, a `Component_Status` its name, and an array type a JSON array.

### Changed

- **Breaking:** remove `ComponentStatusT` and `COMPONENT_STATUS_MAP`. A component status travels as its name, for example `READY`, as the XML profiles type it.
- **Breaking:** remove the `openrois.interfaces.contract` module: `ComponentContract`, its request and response models, `EventEnvelope`, `EventSink` and the error classes, with their schemas and the `contract` module of `schema/manifest.json`. Engines and clients exchange the params and result models of the method catalog, and the component contract of an engine is part of `openrois-engine`.

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

[unreleased]: https://github.com/openrois/openrois/compare/interfaces-v0.1.0-alpha.4...HEAD
[0.1.0a4]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.4
[0.1.0a3]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.3
[0.1.0a2]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.2
[0.1.0a1]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.1
