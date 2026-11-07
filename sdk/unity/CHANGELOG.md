# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `RoISClient`, a client for an OpenRoIS engine over WebSocket, for Unity 6000.0 and later. It has one method per operation of the RoIS method catalog, each taking the IDL parameters in IDL order, returning a `Task` of the out parameters as generated models, and taking an optional `CancellationToken` last:
  - System: `RoISClient.ConnectAsync(url, requestTimeout, connectTimeout, cancellationToken)`, `DisconnectAsync()`, `GetProfileAsync(condition)` and `GetErrorDetailAsync(errorId, condition)`.
  - Command: `SearchAsync(condition)`, `BindAsync(componentRef)`, `BindAnyAsync(condition)`, `ReleaseAsync(componentRef)`, `GetParameterAsync(componentRef)`, `SetParameterAsync(componentRef, parameters)`, `ExecuteAsync(commandUnitList)` and `GetCommandResultAsync(commandId, condition)`.
  - Query: `QueryAsync(queryType, condition)`.
  - Event: `SubscribeAsync(eventType, condition)`, `UnsubscribeAsync(subscribeId)` and `GetEventDetailAsync(eventId, condition)`.
- `await using` runs `DisconnectAsync()` when a block ends. `DisconnectAsync()` is safe to call twice, in turn or overlapping.
- Every result is read through the generated models of `OpenRoIS.Interfaces`. A result whose return code is a failure raises `RoISException`, which carries the return code and the method. The client does not validate params, so an invalid value comes back from the engine as an `RpcException`.
- `GetProfileAsync()` returns an `EngineProfile`: the engine profile together with the profile of every component it lists, keyed by fully qualified ref.
- `ExecuteAsync()` runs commands in order. A `ConcurrentCommands` item gives its commands by branch: the branches run at the same time and each branch runs its commands in order. The engine assigns each command's id, and `ExecuteAsync()` returns the ids from the engine's answer, in order, branch by branch.
- `On(name, listener)` and `Off(name, listener)`: `rois.event.notify_event`, `rois.command.completed`, `rois.system.notify_error` and `rois.system.profile_changed` with their params as generated models, `close` with the close code and reason, and `error` with the exception. The README teaches how to wait for a command: add the listener before `ExecuteAsync()`, record each status by command id, and read it by the ids in the reply.
- Listeners run in the `SynchronizationContext` that was current at `ConnectAsync()`, which on the Unity main thread is the main thread, so they can call Unity APIs. The runtime assembly has no engine references.
- A message that cannot be used, and a listener that throws, reach the `error` listeners, or the log if there are none: the player log in a player and the Console window in the Editor. Neither stops the client.
- In the Editor, every client ends when Play Mode ends and before an assembly reload, also with domain reload off, and `ConnectAsync()` fails while Play Mode is ending. The Editor waits at most 1 second for an engine that stopped answering, then drops the connection.
- `WebSocketTransport` (`OpenRoIS.Sdk.Transport`), under `client.Transport`, with a raw `SendAsync` for methods outside the catalog, and request and connect timeouts as `TimeSpan` values (30 and 10 seconds by default). It accepts messages of up to 16 MiB, and a larger one closes the connection with code 1009.
- The exceptions `TransportException`, `RoISConnectionException`, `RequestTimeoutException` and `RpcException`.
- The JSON-RPC 2.0 layer of the SDK, in the namespace `OpenRoIS.Sdk.JsonRpc`, for an application that manages its own socket. `JsonRpcBuilder` builds request and notification strings, `JsonRpcParser` parses an incoming message into a request, a response, an error or a notification, and `JsonRpcRequest`, `JsonRpcResponse`, `JsonRpcError`, `JsonRpcErrorObject`, `JsonRpcNotification`, `JsonRpcMessage`, `JsonRpcMessageType` and `JsonRpcErrorCode` model the messages.
- The RoIS message types and the CQL2-Text `Condition` builders of `OpenRoIS.Interfaces` 0.1.0-alpha.6, bundled in the package with `System.Text.Json` 8.0.6 and the assemblies it needs, so the package compiles in a clean Unity project. A Unity that ships its own `System.Text.Json`, such as 6000.6, uses its own copy.
- Support for stripped builds: the assemblies that `System.Text.Json` reads by reflection are preserved. Mono players need a Managed Stripping Level of Medium or lower.
- A `Navigation Session` sample, which runs connect, bind, execute and the completed notification against the mock adapter.

[unreleased]: https://github.com/openrois/openrois/tree/dev/sdk/unity
