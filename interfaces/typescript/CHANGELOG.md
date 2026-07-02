# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[unreleased]: https://github.com/openrois/openrois/compare/main...HEAD
[0.1.0-alpha.2]: https://github.com/openrois/openrois/releases/tag/v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/openrois/openrois/releases/tag/v0.1.0-alpha.1