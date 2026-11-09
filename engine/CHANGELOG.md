# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- A parent engine that reconnects, such as a restarted gateway above a running adapter, can name the same command ids again. Before, a valid command whose id the parent had used before it left ended with `ERROR`. An engine now forgets the commands of its parent when the parent's session ends.

## [0.1.0a4] - 2026-11-09

### Changed

- **Breaking:** the engine reaches its components through `ComponentSource`, in `openrois.engine.source`, whose operations carry the names of the RoIS operations they serve: `execute`, `set_parameter`, `get_parameter`, `get_command_result`, `query`, `subscribe`, `unsubscribe`, `get_event_detail` and `get_error_detail`. `LocalComponents` and `ChildEngine` implement it. Code that implements or calls `ComponentContract` from `openrois.engine.contract` uses `ComponentSource`, with `execute` for `run`, `get_command_result` for `command_result`, `get_event_detail` for `event_detail` and `get_error_detail` for `error_detail`. Adapters and gateways built on `Engine` need no change.

## [0.1.0a3] - 2026-11-08

### Fixed

- `pydantic` 2.10 or later is required, because `openrois.engine` does not import with earlier versions, which the declared floor of 2.0 allowed.
- `rois.command.release` also aborts the caller's commands on the component that are still waiting their turn in an `execute` sequence or branch. They complete with `ABORT` at the release and never start. Before, they still ran once their turn came, even after another session had bound the component. The engine that holds the binds needs this release, which for clients of a gateway is the gateway.

## [0.1.0a2] - 2026-11-06

### Fixed

- A second client of a gateway can subscribe to an event another client already subscribes to. It got `ERROR`, because the child engine returned the first subscription for it. Adapters need this release too, since the fix is in the child engine.

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

[unreleased]: https://github.com/openrois/openrois/compare/engine-v0.1.0-alpha.4...HEAD
[0.1.0a4]: https://github.com/openrois/openrois/releases/tag/engine-v0.1.0-alpha.4
[0.1.0a3]: https://github.com/openrois/openrois/releases/tag/engine-v0.1.0-alpha.3
[0.1.0a2]: https://github.com/openrois/openrois/releases/tag/engine-v0.1.0-alpha.2
[0.1.0a1]: https://github.com/openrois/openrois/releases/tag/engine-v0.1.0-alpha.1
