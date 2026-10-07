# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Engine`, the recursive RoIS HRI Engine. It answers the 16 methods of the RoIS method catalog for the components it hosts in its process and for those of its child engines, so one class serves an adapter, a gateway and a middle tier. It selects components by CQL2-Text condition, aggregates the profiles of its child engines as sub profiles, reserves actuation components for the session that binds them, and routes every id to the engine that assigned it.
- Command sequences: `execute` checks the whole sequence first, then runs the items in order with their `delay_time`, runs the commands of a `ConcurrentCommands` item at the same time, each after its own `delay_time`, stops at the first command that ends other than OK and completes the commands after it with ABORT. A delay counts once however deep the component. Every command sends one `rois.command.completed` to the session that started it, and `get_command_result` reads its results.
- Engine-assigned ids that start with the engine id, `engine_id/sub-1` for example, so a service application or an agent sees which engine owns each subscription, event and set_parameter command. `execute` refuses a client's command id in that namespace.
- `LocalComponents`, which hosts components written with `openrois-components-core` or of the same shape (`LocalComponent`). It stores their parameters from the profile defaults, runs the `@on_set_parameter` hook, answers `component_status` from the state of each component, applies the timeout of each command profile, aborts a running `start` on `stop` or on a new `start`, and keeps events for `get_event_detail` until they expire. Components emit events from any thread.
- `ChildEngine`, which reaches a child engine with the same catalog requests a client sends, reads its profile again when the child sends `rois.system.profile_changed`, checks the engine ids of every profile and the ids of every reply, and ends a subscription whose reply came after its caller stopped waiting.
- `ComponentContract`, the interface behind which the components of an engine live, and `Session`, a client of an engine or its parent engine.
- `WsServer`, which serves child engines on `/adapter` and clients on any other path of one port. It discovers each child engine with `rois.system.get_profile`, refuses an empty, slashed or duplicate engine id and a ref the child does not own with close code 1008, at discovery and when the child's profile changes, and releases a client's bindings and subscriptions when it disconnects. Each request runs in its own task, and a reply always goes out before the notifications it causes. It answers PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS with the issues as data, and INTERNAL_ERROR, binds loopback by default, and closes every connection with code 1001 when it stops.
- `WsClient`, which connects an adapter to a gateway, serves it through a trusted session, spins the rclpy nodes of its components when rclpy is installed, and reconnects with a growing delay.
- Type information for every public name (`py.typed`), checked with mypy in strict mode.
