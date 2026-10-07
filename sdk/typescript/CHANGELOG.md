# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `RoISClient`, a client for an OpenRoIS engine over WebSocket, for browsers and Node.js. It has one method per operation of the RoIS method catalog, each taking the IDL parameters in IDL order and returning the out parameters:
  - System: `RoISClient.connect(url)`, `disconnect()`, `getProfile(condition?)` and `getErrorDetail(errorId, condition?)`.
  - Command: `search(condition?)`, `bind(ref)`, `bindAny(condition?)`, `release(ref)`, `getParameter(ref)`, `setParameter(ref, parameters)`, `execute(commandUnitList)` and `getCommandResult(commandId, condition?)`.
  - Query: `query(queryType, condition?)`.
  - Event: `subscribe(eventType, condition?)`, `unsubscribe(subscribeId)` and `getEventDetail(eventId, condition?)`.
- Validation of every call against the method catalog of `@openrois/interfaces`: params before they are sent, results when they arrive. A result whose return code is a failure raises `RoISError`, which carries the return code and the method.
- `getProfile()` returns the engine profile together with the profile of every component it lists, keyed by fully qualified ref.
- `execute()` runs commands in order and groups of commands at the same time. Each command's `command_id` defaults to a UUID, and `execute()` returns the `command_id` of every command in order.
- Typed events, with validated params for each catalog notification: `rois.event.notify_event`, `rois.command.completed`, `rois.system.notify_error` and `rois.system.profile_changed`. Each event also arrives under its own event type, for example `reached_target`. The `notification`, `close` and `error` events carry the JSON-RPC envelope, the close code and reason, and the error.
- The builders for CQL2-Text conditions from `@openrois/interfaces`: `componentRef`, `componentType`, `componentTypeUrn`, `eq`, `like`, `allOf` and `quote`, with the property names `COMPONENT_REF` and `COMPONENT_TYPE`.
- `WebSocketTransport` (`@openrois/sdk/transport`), with request and connect timeouts, a custom WebSocket factory, and the `ConnectionError`, `RequestTimeoutError` and `RpcError` errors.
- The JSON-RPC 2.0 envelope schemas and `JsonRpcErrorCode` (`@openrois/sdk/jsonrpc`).
