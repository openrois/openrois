# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The JSON-RPC 2.0 layer of the OpenRoIS SDK for Unity, in the namespace `OpenRoIS.Sdk.JsonRpc`. `JsonRpcBuilder` builds request and notification strings, `JsonRpcParser` parses an incoming message into a request, a response, an error or a notification, and `JsonRpcRequest`, `JsonRpcResponse`, `JsonRpcError`, `JsonRpcNotification`, `JsonRpcMessage` and `JsonRpcErrorCode` model the messages. Use it with the RoIS message types of `OpenRoIS.Interfaces` to speak to an OpenRoIS gateway. The high-level `RoISClient` and its WebSocket transport are not in this release.

[unreleased]: https://github.com/openrois/openrois/tree/dev/sdk/csharp
