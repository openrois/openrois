# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The `openrois-mcp` command and `python -m openrois.mcp`: an MCP server over stdio, or streamable HTTP on loopback by default, that serves the components behind an OpenRoIS gateway to an AI agent through one RoIS session.
- Tools to discover and observe: `list_components` with each component's status for the session, `describe_component`, `query`, `get_parameters`, `subscribe`, `unsubscribe`, `get_events` with a cursor, `wait_for_event`, `get_error_detail` and `command_status`.
- Tools to act, offered only with `--allow-actions`: `bind` with an optional wait for a busy component, `release`, `set_parameters` and `run_commands`, which takes plain JSON values, needs a bind by default, binds all or nothing with `auto_bind`, and sets parameters right before a command with a `set_parameter` step.
- `wait_for_event` that starts, without `since`, at the cursor the last tool returned, so an event a component sends while a command runs reaches the wait after it.
- Refusals and results an agent can act on: the step, the component, the return code and a hint that depends on the call, such as `OUT_OF_RESOURCES` when another client holds an actuation component, with the advice to ask the user before waiting for it. A command that ends `ERROR` carries the component's status and the errors its engine reported, a command that ends `ABORT` after a failed one names it, and a refused value names the queries that list the valid ones.
- `describe_component` shows each parameter's `initial_value`, and the current value while the session holds the component.
- Binds and subscriptions that follow the engine: when the engine of a component leaves the gateway or reconnects, a `lost` entry and a notice name the binds and subscriptions it dropped. When the gateway connection drops, a wait on commands ends at once with `CONNECTION_LOST`, and the next tool response says the old session is gone.
- `release` names the commands that ended `ABORT` with it, and any that still run.
- `--allow` patterns that limit the components an agent may act on, an optional idle release of binds, and a clean exit when the agent closes the server: it stops the components the session started, ends its subscriptions and releases its binds, within five seconds.
- Settings as flags or `OPENROIS_MCP_*` environment variables: the gateway URL, the command and request timeouts, the event buffer size (500 by default), the idle release, the transport, the host and the port.
- A warning in the log when streamable HTTP listens on an address beyond loopback, since the server has no authentication.
- The resources `rois://components`, `rois://components/{ref}` and `rois://session`.

[unreleased]: https://github.com/openrois/openrois/tree/dev/services/mcp
