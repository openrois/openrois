# Changelog
All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `RoISClient`: a client for Unity and any .NET runtime with `netstandard2.1`, speaking
  RoIS JSON-RPC over a `ClientWebSocket`. System, Command, Query, and Event operations as
  `async` methods, events, completions, and errors as C# events delivered on the calling
  `SynchronizationContext` (Unity's main thread), and a `Token` option for gateways that
  authenticate.
- Streaming Interface: `ConnectStreamAsync()`, `DisconnectStreamAsync()`,
  `SuspendStreamAsync()`, `ResumeStreamAsync()`, `QueryStreamStatusAsync()`, and the
  `StreamStatusChanged` event.
- `Samples/Example`: a MonoBehaviour that connects, discovers, and speaks through
  `SpeechSynthesis`.
- A plain .NET test project (`DotNetTests~`) that verifies the client against a fake
  gateway outside the Unity editor.

### Changed

- Version aligned with the rest of the monorepo (0.1.0-alpha.3).

## [0.1.0] - 2026-07-15

### Added

- Unity package scaffold (`com.openrois.sdk`) with the assembly definition and the
  package manifest.
