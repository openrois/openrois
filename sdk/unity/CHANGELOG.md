# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The JSON-RPC 2.0 layer of the OpenRoIS SDK for Unity, in the namespace `OpenRoIS.Sdk.JsonRpc`, for Unity 6000.0 and later. `JsonRpcBuilder` builds request and notification strings, `JsonRpcParser` parses an incoming message into a request, a response, an error or a notification, and `JsonRpcRequest`, `JsonRpcResponse`, `JsonRpcError`, `JsonRpcErrorObject`, `JsonRpcNotification`, `JsonRpcMessage`, `JsonRpcMessageType` and `JsonRpcErrorCode` model the messages.
- The RoIS message types of `OpenRoIS.Interfaces`, bundled in the package with `System.Text.Json` 8.0.6 and the assemblies it needs, so the package compiles in a clean Unity project. A Unity that ships its own `System.Text.Json`, such as 6000.6, uses its own copy.
- The `execute` messages in the bundled types: `ExecuteParams` and `ExecuteResult` read and write a command unit list, including branches.
- Support for stripped builds: the assemblies that `System.Text.Json` reads by reflection are preserved. Mono players need a Managed Stripping Level of Medium or lower.
- A `JSON-RPC Round Trip` sample.

[unreleased]: https://github.com/openrois/openrois/tree/dev/sdk/unity
