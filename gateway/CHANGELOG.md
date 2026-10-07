# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The `openrois-gateway` command and `python -m openrois.gateway`: the main RoIS HRI Engine on a WebSocket port, with child engines on `/adapter` and clients on any other path.
- Configuration from a YAML file, `OPENROIS_GATEWAY_*` environment variables and command-line flags, each overriding the one before: the host (loopback by default), the port, the engine id, the log level and the child request timeout.
- A graceful stop on SIGTERM and SIGINT that closes every connection with code 1001 and exits with code 0. Exit code 1 reports a gateway that cannot start, and exit code 2 an invalid configuration.
- `Gateway` and `GatewayConfig`, to run the gateway inside another program.
- A container image, built from `gateway/Dockerfile`, that runs the gateway as a non-root user and listens on every interface inside the container.
