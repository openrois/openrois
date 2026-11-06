# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The JSON-RPC 2.0 layer of the OpenRoIS SDK for Unity, in the namespace `OpenRoIS.Sdk.JsonRpc`. `JsonRpcBuilder` builds request and notification strings, `JsonRpcParser` parses an incoming message into a request, a response, an error or a notification, and `JsonRpcRequest`, `JsonRpcResponse`, `JsonRpcError`, `JsonRpcNotification`, `JsonRpcMessage` and `JsonRpcErrorCode` model the messages. Use it with the RoIS message types of `OpenRoIS.Interfaces` to speak to an OpenRoIS gateway. The high-level `RoISClient` and its WebSocket transport are not in this release.
- `LICENSE.md` (Apache-2.0) and `NOTICE.md` in the package, and the `license` field in `package.json`, as the Unity Package Manager requires a license file or field.

### Changed

- **BREAKING CHANGE:** the package directory moved from `sdk/csharp/` to `sdk/unity/`. Update the `file:` path in the `manifest.json` of a Unity project that uses a local copy. The package name `org.openrois.sdk` does not change.

[unreleased]: https://github.com/openrois/openrois/tree/dev/sdk/unity
