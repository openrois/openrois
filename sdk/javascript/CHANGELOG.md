# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `RoISClient`, a client for an OpenRoIS engine over WebSocket, for browsers and Node.js 22.12 or later, as one ES module build that `require` can also load. It has one method per operation of the RoIS method catalog, each taking the IDL parameters in IDL order and returning the out parameters:
  - System: `RoISClient.connect(url, options?)`, `disconnect()`, `getProfile(condition?)` and `getErrorDetail(errorId, condition?)`.
  - Command: `search(condition?)`, `bind(ref)`, `bindAny(condition?)`, `release(ref)`, `getParameter(ref)`, `setParameter(ref, parameters)`, `execute(commandUnitList)` and `getCommandResult(commandId, condition?)`.
  - Query: `query(queryType, condition?)`.
  - Event: `subscribe(eventType, condition?)`, `unsubscribe(subscribeId)` and `getEventDetail(eventId, condition?)`.
- `await using` runs `disconnect()` when a block ends. `disconnect()` is safe to call twice, in turn or overlapping.
- Validation of every call against the method catalog of `@openrois/interfaces`, which is required at 0.1.0-alpha.6 or later: params before they are sent, results when they arrive. A result whose return code is a failure raises `RoISError`, which carries the return code and the method.
- `getProfile()` returns the engine profile together with the profile of every component it lists, keyed by fully qualified ref.
- `execute()` runs commands in order. A ConcurrentCommands item gives its commands in `branch_list`: the branches run at the same time and each branch runs its commands in order. The engine assigns each command's `command_id`, and `execute()` returns the ids from the engine's answer, in order, branch by branch.
- `on(name, listener)` and `off(name, listener)`, typed for each name: `rois.event.notify_event`, `rois.command.completed`, `rois.system.notify_error` and `rois.system.profile_changed` with their validated params, `close` with the close code and reason, and `error` with the error. The README teaches how to wait for a command: add the listener before `execute()`, record each status by `command_id`, and read it by the ids in the reply.
- A message that cannot be used, and a listener that throws, reach the `error` listeners, or `console.error` if there are none. Neither stops the client.
- The builders for CQL2-Text conditions, exported from `@openrois/sdk`: `componentRef`, `componentType`, `componentTypeUrn`, `eq`, `like`, `allOf` and `quote`, with the property names `COMPONENT_REF` and `COMPONENT_TYPE`.
- `WebSocketTransport` (`@openrois/sdk/transport`), under `client.transport`, with a raw `send` for methods outside the catalog, request and connect timeouts in milliseconds (30 and 10 seconds by default), and a custom WebSocket factory. The errors `TransportError`, `ConnectionError`, `RequestTimeoutError` and `RpcError` come from both entry points.

[unreleased]: https://github.com/openrois/openrois/tree/dev/sdk/javascript
