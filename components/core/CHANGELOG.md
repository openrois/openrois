# Changelog

All notable changes to `openrois-components-core` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `conformance`: `conformance_report(engine)` and `assert_conformant(engine)` check an
  engine and its components against the RoIS basic component profiles (lifecycle
  commands, `component_status`, and the messages each profile declares), for use in
  adapter test suites. `AudioStreaming` and `VideoStreaming` profiles included.

### Changed

- Version aligned with the rest of the monorepo (0.1.0a3).

