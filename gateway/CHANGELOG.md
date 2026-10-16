# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The `openrois-gateway` command and `python -m openrois.gateway`: the main RoIS HRI Engine on a WebSocket port, with child engines on `/adapter` and clients on any other path.
- Every method of the RoIS method catalog, served to clients for the components of every child engine, with the RoIS behavior of `openrois-engine`: a client sends `rois.system.connect` first, binds every component it commands, reads the command ids of an `execute` from its result, and runs `ConcurrentCommands` as branches. Binds, command ids and the abort of a client's commands when it releases a component or goes away are held at the gateway for every child engine, and errors from the adapters reach the clients concerned.
- Configuration from a YAML file, `OPENROIS_GATEWAY_*` environment variables and command-line flags, each overriding the one before: the host (loopback by default), the port, the engine id, the log level and the child request timeout.
- A graceful stop on SIGTERM and SIGINT that closes every connection with code 1001 and exits with code 0. Exit code 1 reports a gateway that cannot start, and exit code 2 an invalid configuration.
- `Gateway` and `GatewayConfig`, to run the gateway inside another program.
- A container image, built from `gateway/Dockerfile`, that runs the gateway as a non-root user and listens on every interface inside the container. `compose.yaml` runs it with the mock adapter.
- The smoke script, `gateway/scripts/smoke.py`, which checks a running gateway end to end: it connects, binds, executes and reads the command id the gateway assigns.

[unreleased]: https://github.com/openrois/openrois/tree/dev/gateway
