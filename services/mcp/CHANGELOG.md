# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The `openrois-mcp` command and `python -m openrois.mcp`: an MCP server over stdio, or streamable HTTP on loopback, that serves the components behind an OpenRoIS gateway to an AI agent through one RoIS session.
- Tools to discover and observe: `list_components` with each component's status for the session, `describe_component`, `query`, `get_parameters`, `subscribe`, `unsubscribe`, `get_events` with a cursor, `wait_for_event`, `get_error_detail` and `command_status`.
- Tools to act, offered only with `--allow-actions`: `bind` with an optional wait for a busy component, `release`, `set_parameters` and `run_commands`, which takes plain JSON values, needs a bind by default and binds all or nothing with `auto_bind`.
- Refusals an agent can act on: the step, the component, the return code and a hint, such as `OUT_OF_RESOURCES` when another session holds an actuation component.
- `--allow` patterns that limit the components an agent may act on, an optional idle release of binds, and the release of every bind when the agent closes the server.
- The resources `rois://components`, `rois://components/{ref}` and `rois://session`.

[unreleased]: https://github.com/openrois/openrois/tree/dev/services/mcp
