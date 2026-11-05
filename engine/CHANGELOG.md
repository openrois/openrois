# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0a1] - 2026-11-05

### Added

- `Engine`, the recursive RoIS HRI Engine. It answers the 16 methods and 4 notifications of the RoIS method catalog for its local components and its child engines, so one class serves an adapter, a gateway and a middle tier. It implements the RoIS interfaces, profiles and common messages (CP1 to CP3) as section 16 of `docs/rois-reference.md` records them, without a conformance claim.
- Sessions, and binds on every component by RoSO function: one bind at a time on actuation components, one per session on the others.
- Command sequences with branches, engine-assigned command ids, start timeouts, `set_parameter` and the RoIS_Common default.
- `component_status` per session, and the error channel: `raise_status`, `clear_status`, `rois.system.notify_error` and `get_error_detail`.
- Queries and events with arguments, and component selection by CQL2-Text condition. AudioStreaming and VideoStreaming are served like any other profile.
- `LocalComponents` for the components of a process, `ChildEngine` for a child engine, and `ComponentContract`, the interface behind which both live.
- `WsServer` for a gateway and `WsClient` for an adapter, which reconnects with a growing delay.
- The adapter configuration loader, `openrois.engine.config`, which reads `adapter.yaml`, the environment and flags.
- Type information for every public name (`py.typed`).
- `openrois-interfaces` 0.1.0a5 or later is required, because the engine reads the `Branch` model that release introduced.

[unreleased]: https://github.com/openrois/openrois/compare/engine-v0.1.0-alpha.1...HEAD
[0.1.0a1]: https://github.com/openrois/openrois/releases/tag/engine-v0.1.0-alpha.1
