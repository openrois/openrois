# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Engine`, the recursive RoIS HRI Engine. With child engines it is a main HRI Engine, with local components a sub HRI Engine, and with both a middle tier. It routes every call to the engine that owns the component, aggregates the profiles, and holds the bindings.
- `ComponentRegistry`, the in-process side of the Component Contract for local components, and `ChildEngineProxy`, its WebSocket side for one connected child engine.
- `EventEmitter`, which delivers events to subscribers and accepts them from any thread.
- `WsServer`, which serves child engines on `/adapter` and clients on any other path of one port. It discovers each child engine, refuses an empty, slashed or duplicate engine id with close code 1008, relays events to the client that subscribed, and releases a client's bindings and subscriptions when it disconnects. Each request runs in its own task. It answers PARSE_ERROR, INVALID_REQUEST, INVALID_PARAMS and INTERNAL_ERROR, binds loopback by default, and closes every connection with code 1001 when it stops.
- `WsClient`, which connects an adapter to a gateway, answers each request in its own task, and reconnects with exponential backoff.
- `read_profile` and `component_config`, which load a profile YAML file and slice the configuration of each component out of it.
