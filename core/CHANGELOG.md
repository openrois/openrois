# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `ComponentRegistry` and `SubEngine` now implement the `ComponentContract` protocol with
  its typed request and response models (`DiscoverRequest`, `CommandRequest`,
  `QueryRequest`, `SubscribeRequest` and their responses), and `Engine` dispatches through
  that protocol only.
- `EventEmitter` delivers events to the `EventSink` passed at subscribe time instead of
  writing to a WebSocket directly. Its constructor takes only the event loop.
- The gateway discovers an adapter through `rois.system.get_profile` and answers
  `rois.command.search` with the standard `component_ref_list` only.
- Command types are validated against the RoIS `CommandType` enum; unknown ones return
  `BAD_PARAMETER`.
- Subscriptions held by a client are released upstream when the client disconnects.

### Fixed

- Adapter discovery no longer deadlocks: the adapter receive loop runs while the gateway
  awaits the profile.
- Compatible with `websockets` 14 and later (connection path and state accessors).

### Added

- `benchmarks/latency.py`: control-plane latency through the gateway and direct to an
  adapter (query, execute, event delivery), p50/p95/p99 over loopback.
- Authentication and authorization at the gateway: `WsServer(engine, auth=AuthConfig(...))`
  verifies a JSON Web Token at the WebSocket upgrade (`Authorization: Bearer` header or
  `token` query parameter, HS256 or asymmetric algorithms, issuer and audience checks),
  the `roles` claim (viewer, maintenance, operator, administrator, adapter) decides which
  RoIS operations a connection may call, and the `scope` claim limits the component refs
  it may see and address. `openrois-gateway --auth-key ...` turns it on; `--tls-cert` and
  `--tls-key` serve `wss://`. `WsClient(..., token=...)` presents the adapter's token.
- `rois.command.bind_any`, `rois.command.get_parameter`, `rois.command.get_command_result`,
  `rois.system.get_error_detail`, and `rois.event.get_event_detail`.
- `rois.command.completed` and `rois.system.notify_error` notifications. Components report
  completion with `self.parent.complete(command_id, status)` (thread-safe) or
  `complete_async`; a handler that raises produces a `notify_error` for the caller.
- Regression test suite (`tests/`): engine dispatch, bindings, events, and a gateway plus
  adapter round trip over a real WebSocket.
