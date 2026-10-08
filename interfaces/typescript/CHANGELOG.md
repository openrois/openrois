# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add `SPEECH_SYNTHESIS_PROFILE` to `./components`, generated from `schema/profiles.json`. The constant is the full profile of the SpeechSynthesis type: its XML profile with the RoIS_Common messages listed first, and the RoSO function `actuation`.

## [0.1.0-alpha.4] - 2026-10-08

### Added

- Add the profile constants of the basic components to `./components`: `ROIS_COMMON_PROFILE`, `NAVIGATION_PROFILE`, `PERSON_DETECTION_PROFILE`, `REACTION_PROFILE` and `SYSTEM_INFORMATION_PROFILE`, generated from `schema/profiles.json`. Each constant is the full profile of its type: the XML profile with the RoIS_Common messages listed first, and the RoSO function.

### Changed

- **Breaking:** remove the `ComponentStatusT` type. A component status travels as its name, for example `READY`, as the XML profiles type it.
- **Breaking:** remove the `./contract` subpath export and its names from the package root: `ComponentContract`, its request and response schemas, `EventEnvelopeSchema` and the error classes. Clients and engines exchange the params and result schemas of `./catalog`.

## [0.1.0-alpha.3] - 2026-10-08

### Added

- Add the `./catalog` subpath export with a params and a result schema for each of the 16 `rois.*` methods, `RoISMethods`, the `RoISMethodMap` type, `RoISMethodSchemas` and `JsonRpcErrorCode`, generated from `schema/catalog.json`.
- Add the notification names and params to `./catalog`: `RoISNotifications`, the `RoISNotificationMap` type and `RoISNotificationSchemas`, for `rois.system.notify_error`, `rois.command.completed`, `rois.event.notify_event` and `rois.system.profile_changed`. Add `RoISCommandTypes`, the standard command names.
- Add `ProfileChangedParamsSchema`, `GetProfileResult.component_profiles` (component profiles keyed by fully qualified ref), `HRIComponentProfile.function` with `ComponentFunctionSchema`, and `NotifyEventParams.results`. All three fields are OpenRoIS extensions.
- Add the `./condition` subpath export, a hand-written port of the Python `openrois.interfaces.condition` module: `parseCondition`, `Condition`, `Comparison` and `ConditionError` read and match conditions in the CQL2-Text subset, and `eq`, `like`, `allOf`, `quote`, `componentRef`, `componentType` and `componentTypeUrn` build them.
- The generator writes a JSON Schema map (`additionalProperties` with a schema) as `z.record(z.string(), ...)` and a `Record<string, ...>` type.

### Changed

- Describe `ConditionT` and every `condition` field as the OpenRoIS subset of CQL2-Text.
- **Breaking:** `CommandType` is a `string` alias, and `CommandTypeSchema` is removed. `command_type` is `z.string()`, as in the IDL and the XSD, because a component may define commands of its own. `RoISCommandTypes` lists the standard names.
- **Breaking:** remove `component_profiles` from `HRIEngineProfileType`, which now matches the XSD. Read the component profiles from `GetProfileResult.component_profiles`.
- **Breaking:** rename `NotifyErrorEventSchema` to `NotifyErrorParamsSchema`, `CompletedEventSchema` to `CompletedParamsSchema` and `NotifyEventPayloadSchema` to `NotifyEventParamsSchema`, with their types. The event notification is `rois.event.notify_event` instead of `rois.event.notify`.
- **Breaking:** every generated type is defined once, in the module that owns it, and other modules import it. Array aliases such as `ArgumentList` are inlined, so `ArgumentListSchema` is no longer exported. `ArgumentList` remains as a type alias.
- **Breaking:** rename `BusAdapter` to `ComponentContract` and `BusAdapterError` to `ComponentContractError` (closes #5). The `./bus` subpath export is now `./contract`, and the generated models moved to `src/generated/contract-models.ts`.

## [0.1.0-alpha.2] - 2026-07-02

### Added

- Emit zod schemas + inferred types for `Reaction` component models.

### Fixed

- Fix generated zod schemas that referenced non-existent schema variables for
  simple type aliases (`RoISIdentifier`, `Integer`, etc.). These are now
  inlined as `z.string()` / `z.number().int()` instead of referencing
  non-existent schema variables.

## [0.1.0-alpha.1] - 2026-06-20

### Added

- Generate `@openrois/interfaces` TypeScript package from 38 JSON Schema files in `interfaces/schema/`.
- Emit zod schemas + inferred types for all core HRI, Common, Service, Profile, Bus, and component models (`PersonDetection`, `Navigation`, `SystemInformation`).
- Hand-write `BusAdapter` interface, `EventSink` type, `BusAdapterError` and `ComponentNotFoundError` error classes.
- ESM package with subpath exports: `.`, `/hri`, `/common`, `/service`, `/profiles`, `/bus`, `/components`.
- Custom generator (`scripts/generate.ts`) handling `$defs`, `$ref`, `anyOf` unions, recursive types, enums, defaults, and `additionalProperties: false`.

[unreleased]: https://github.com/openrois/openrois/compare/interfaces-v0.1.0-alpha.4...HEAD
[0.1.0-alpha.4]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.4
[0.1.0-alpha.3]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.3
[0.1.0-alpha.2]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/openrois/openrois/releases/tag/interfaces-v0.1.0-alpha.1
