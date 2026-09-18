# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `RoISClient.connect(url, { token })` presents a JSON Web Token at the WebSocket
  upgrade for gateways that authenticate.
- Streaming Interface: `connectStream()`, `disconnectStream()`, `suspendStream()`,
  `resumeStream()`, and `queryStreamStatus()`. Stream status changes arrive through
  `client.on("rois.stream.notify_status", handler)`.

### Changed

- Version aligned with the rest of the monorepo (0.1.0-alpha.3).

