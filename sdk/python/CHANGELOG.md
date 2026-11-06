# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `RoISClient`, an asyncio client for an OpenRoIS engine over WebSocket, on Python 3.12 or later. It has one method per operation of the RoIS method catalog, each taking the IDL parameters in IDL order and returning the out parameters as interface models:
  - System: `RoISClient.connect(url, *, request_timeout, connect_timeout)`, `disconnect()`, `get_profile(condition="")` and `get_error_detail(error_id, condition="")`.
  - Command: `search(condition="")`, `bind(component_ref)`, `bind_any(condition="")`, `release(component_ref)`, `get_parameter(component_ref)`, `set_parameter(component_ref, parameters)`, `execute(command_unit_list)` and `get_command_result(command_id, condition="")`.
  - Query: `query(query_type, condition="")`.
  - Event: `subscribe(event_type, condition="")`, `unsubscribe(subscribe_id)` and `get_event_detail(event_id, condition="")`.
- `RoISClient.connect()` works with `await` and with `async with`, which runs `disconnect()` when the block ends. `disconnect()` is safe to call twice, in turn or overlapping.
- Validation of every call against the method catalog of `openrois-interfaces`, which is required at 0.1.0a6 or later: params before they are sent, results when they arrive. Inputs take a model or a mapping. Invalid params and results raise `pydantic.ValidationError`. A result whose return code is a failure raises `RoISError`, which carries the return code and the method.
- `get_profile()` returns an `EngineProfile`: the engine profile together with the profile of every component it lists, keyed by fully qualified ref.
- `execute()` runs commands in order. A ConcurrentCommands item gives its commands in `branch_list`: the branches run at the same time and each branch runs its commands in order. The engine assigns each command's `command_id`, and `execute()` returns the ids from the engine's answer, in order, branch by branch.
- `on(name, listener)` and `off(name, listener)`, typed for each name: `rois.event.notify_event`, `rois.command.completed`, `rois.system.notify_error` and `rois.system.profile_changed` with their validated params, `close` with the close code and reason, and `error` with the exception. A plain function runs inline in the reader of the socket, and a coroutine function runs in a task of its own, where it can await a call. The README teaches how to wait for a command: add the listener before `execute()`, record each status by `command_id`, and read it by the ids in the reply.
- A message that cannot be used, and a listener that raises, reach the `error` listeners, or the `openrois.sdk.transport` logger if there are none. Neither stops the client.
- Cancellation with `asyncio.timeout`, `asyncio.wait_for` or a `TaskGroup`. A cancelled call leaves the client working, and a cancelled `connect()` ends at once.
- The builders for CQL2-Text conditions, exported from `openrois.sdk`: `component_ref`, `component_type`, `component_type_urn`, `eq`, `like`, `all_of` and `quote`, with the property names `COMPONENT_REF` and `COMPONENT_TYPE`.
- `WebSocketTransport` (`openrois.sdk.transport`), under `client.transport`, with a raw `send` for methods outside the catalog, and request and connect timeouts in seconds (30 and 10 by default). It accepts messages of up to 16 MiB, and a larger one closes the connection with code 1009.
- The errors `TransportError`, `RoISConnectionError`, `RequestTimeoutError` and `RpcError`. `RoISConnectionError` is also a builtin `ConnectionError`, and `RequestTimeoutError` is also a builtin `TimeoutError`.
- Type information for every public name (`py.typed`).

[unreleased]: https://github.com/openrois/openrois/tree/dev/sdk/python
