# openrois-mcp

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)

An [MCP](https://modelcontextprotocol.io/) server that gives an AI agent the physical robots,
virtual avatars, and digital services behind an [OpenRoIS](https://openrois.org/) gateway, through
the standard interfaces of the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0).

An agent such as Claude Code or Claude Desktop finds the components, reads their profiles,
reads state, follows events and, when you allow it, runs commands. It needs no knowledge of
any robot's own API. The server is built on
[`openrois-sdk`](https://github.com/openrois/openrois/blob/dev/sdk/python/README.md).

> **Alpha, pre-1.0, unstable API.**

## Install

```bash
pip install openrois-mcp
```

From source:

```bash
git clone https://github.com/openrois/openrois.git
pip install -e ./openrois/services/mcp
```

The server needs Python 3.12 or later and a running gateway. The Docker Compose stack at the
repository root serves simulated components through one:

```bash
docker compose up --build -d     # a gateway on ws://127.0.0.1:8765 with the mock adapter
```

## Use It from an Agent

### Claude Code

```bash
claude mcp add openrois -- openrois-mcp --gateway-url ws://127.0.0.1:8765 --allow-actions
```

Leave out `--allow-actions` to let the agent look but not act.

### Claude Desktop

Add the server to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "openrois": {
      "command": "openrois-mcp",
      "args": ["--gateway-url", "ws://127.0.0.1:8765", "--allow-actions"]
    }
  }
}
```

Give the full path of `openrois-mcp` in `command` if Claude Desktop does not find it on its
`PATH`.

## Safety

The gateway does not authenticate connections in the alpha releases, and an agent with
actions allowed can move a physical robot. The server limits what an agent can do:

- **Read-only by default.** `bind`, `release`, `set_parameters` and `run_commands` exist only
  with `--allow-actions`. A read-only server binds nothing, not even for `get_parameters`.
- **An allow list.** `--allow 'reachy_real/%'`, repeatable, limits the components an agent can
  bind, configure and command to the refs that match a CQL2 LIKE pattern. Discovery still shows
  every component.
- **Annotations.** The tools that only read are marked read-only. `run_commands`,
  `set_parameters` and `release` are marked destructive, so an MCP client can ask you before it
  runs them.
- **A clean exit.** When the agent closes the server, it runs `stop` on the components this
  session started and did not stop, such as a person detector, ends its subscriptions,
  releases every bind, which aborts its running commands, and disconnects. Each step is best
  effort within five seconds, so a gateway that does not answer never holds up the exit.
- **Local by default.** stdio needs no port. The streamable-http transport listens on loopback
  unless `--host` says otherwise, and has no authentication either.

## One Server per Agent

The engine tells clients apart by their RoIS session. It gives an actuation component (one
that moves, speaks, or shows) to one session at a time, and sends a command's completion to
the session that ran it. Each server process holds one session.

- With stdio, every agent starts its own server, so every agent has its own session. Two agents
  that want the same robot then take turns through `bind`.
- Agents that share one server share one session. This includes subagents inside one client.
  A bind by one of them covers the others, and the engine cannot tell them apart.
- The engine does not say which session holds a component. An agent learns that it is busy,
  not who has it. The hint of a busy component tells the agent to tell the user and to ask
  before it waits for the component with `bind(wait_seconds)`.

## Tools

| Tool | What it does |
|------|--------------|
| `list_components(pattern?)` | Every component with its type, engine, function, commands, queries and events, its `component_status` for this session (`BUSY` when another session holds it), `held_by_this_session` and `actions_allowed` |
| `describe_component(ref)` | The commands, queries, events and parameters of one component, with their types, argument defaults, read-only flags, each parameter's `initial_value`, and current values when bound |
| `query(ref, query_type)` | Runs a query and returns its results as JSON values |
| `get_parameters(ref)` | The current parameters. An actuation component must be bound first. Another component is bound for the read, only by a server that may act on it |
| `subscribe(ref, event_type)`, `unsubscribe(subscribe_id)` | Follow an event of one component. For a component with a `start` command, the reply says it may send events only once started |
| `get_events(since?, limit?)` | The notifications after a cursor, and the next cursor |
| `wait_for_event(event_type?, ref?, timeout?, since?)` | Waits for a matching event, an error, a loss, or the timeout. Without `since`, it starts at the cursor of the `subscribe`, `run_commands` or `set_parameters` just before it, or else at the newest entry |
| `get_error_detail(error_id)` | The details of an error entry |
| `command_status(command_ids)` | How commands of this session ended, with their results |
| `bind(ref, wait_seconds?)` | Reserves a component. With `wait_seconds`, retries while another session holds it |
| `release(ref)` | Frees a component, and names the commands of this session that ended `ABORT` with it |
| `set_parameters(ref, values, wait?)` | Sets parameters from plain JSON values and waits until they apply |
| `run_commands(steps, wait?, timeout?, auto_bind?)` | Runs commands and parallel groups, and returns how each one ended |

The last four exist only with `--allow-actions`.

`get_events` returns entries of these kinds: `event`, `completed` (a command ended), `error`,
`profile_changed` (components joined or left), `lost` (binds and subscriptions the engine
dropped), `connection_closed` and `idle_release`.

### Waiting for Events

`subscribe`, `run_commands`, `set_parameters`, `get_events` and `wait_for_event` each return a
`cursor`. The first `wait_for_event` without `since` after `subscribe`, `run_commands` or
`set_parameters` starts at the cursor that call returned. So an event a component sends while
a command runs, before the command completes, still reaches the wait that follows, as in
`subscribe`, then `run_commands` with a person detector's `start`, then
`wait_for_event("person_detected")`. Any other wait without `since` starts at the newest entry,
so asking again later waits for a fresh count instead of returning an old one. To read every
entry in turn, pass the `cursor` of the last wait as `since`. A wait that times out returns the
cursor it started at.

Some components, such as a person detector, send events only between their `start` and
`stop` commands. A read-only server cannot start them.

### Running Commands

```json
{
  "steps": [
    {"component_ref": "mock/navigation", "command_type": "start"},
    {
      "branch_list": [
        [{"component_ref": "robot/speech", "command_type": "speak", "arguments": {"text": "Hi"}}],
        [{"component_ref": "robot/head", "command_type": "nod"}]
      ],
      "delay_time": 500
    }
  ]
}
```

A step is a command, or a parallel group whose branches run at the same time, each branch in
order, after `delay_time` milliseconds. Arguments are plain JSON values: the server types them
from the component profile. With `wait` (the default), the call returns when every command has
ended or the timeout passes, with each status: `OK`, `ERROR`, `ABORT`, `TIMEOUT`,
`OUT_OF_RESOURCES`, `RUNNING` for a command that had not ended yet, or `CONNECTION_LOST` when
the gateway connection went during the wait.

A command that did not end `OK` comes with a hint. One that ended `ERROR` also carries the
component's `component_status` and the `error` entries its engine sent after the command
started. One that ended `ABORT` after a failed command names it.

Many commands, such as the `start` of a reaction or of speech, take no arguments and read the
component's parameters instead. A `set_parameter` step sets them in the same call, right
before the command that reads them:

```json
{
  "steps": [
    {"component_ref": "mock/navigation", "command_type": "set_parameter",
     "arguments": {"target_positions": ["kitchen"]}},
    {"component_ref": "mock/navigation", "command_type": "start"}
  ]
}
```

Parameters stay on the component between sessions, so set every parameter a command reads
before each start. `initial_value` in `describe_component` is only the value before anyone set
it.

Every component must be bound by this session first. Otherwise the call fails before anything
is sent:

```json
{"step": "bind", "component_ref": "mock/navigation", "return_code": "NOT_BOUND",
 "hint": "not bound by this session, call bind first"}
```

With `auto_bind`, the server binds the components itself, all or nothing: if a bind fails, it
releases the binds this call made, runs nothing, and names the component and the code, for
example `OUT_OF_RESOURCES` with the hint that another session holds it. A component this
session holds is bound again too, which renews a bind the engine dropped. Binds stay until
`release`, the end of the session, or the idle release.

## Resources

| URI | Content |
|-----|---------|
| `rois://components` | Every component with its type and what it offers |
| `rois://components/{ref}` | One component profile, condensed like `describe_component` |
| `rois://session` | This session's binds, subscriptions, running commands and connection |

## Errors

A RoIS call that does not return `OK` becomes a tool error that names the method, the return
code and what to do, such as `rois.query.query returned UNSUPPORTED for mock/navigation: the
component does not declare this, see describe_component`. The hint of `ERROR` depends on the
call: for a query or a subscribe, the component cannot serve now, for example because its
device is unreachable. For a command operation, the session holds no bind, or the engine
dropped it. A value the component refused names the queries that list valid values, such as
`available_reactions`.

When the engine of a component leaves the gateway or reconnects to it, the engine drops the
binds and subscriptions of every session on its components. The server notices, adds a `lost`
entry that names them, and says so in the `notice` of the next tool response. `bind` always
asks the engine, so binding again works.

When the gateway connection drops, the server does not reconnect in the middle of a call. A
wait on commands ends at once with `CONNECTION_LOST`. The next tool response, even a failed
one, says in its `notice` that the binds and subscriptions of the old session are gone, and
the next call opens a new session.

## Configuration

Each flag has an environment variable, and a flag overrides its variable.

| Flag | Variable | Default | Meaning |
|------|----------|---------|---------|
| `--gateway-url` | `OPENROIS_MCP_GATEWAY_URL` | `ws://127.0.0.1:8765` | The gateway |
| `--allow-actions` | `OPENROIS_MCP_ALLOW_ACTIONS` | off | Offer the tools that act |
| `--allow PATTERN` | `OPENROIS_MCP_ALLOW` (comma-separated) | every component | Components an agent may act on |
| `--command-timeout` | `OPENROIS_MCP_COMMAND_TIMEOUT` | 60 | The longest wait for a command, in seconds |
| `--event-buffer` | `OPENROIS_MCP_EVENT_BUFFER` | 500 | Notifications kept for `get_events` |
| `--idle-release SECONDS` | `OPENROIS_MCP_IDLE_RELEASE` | off | Release a bind with no call on its component for this long |
| `--request-timeout` | `OPENROIS_MCP_REQUEST_TIMEOUT` | 30 | The wait for one RoIS reply, in seconds |
| `--transport` | `OPENROIS_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `--host`, `--port` | `OPENROIS_MCP_HOST`, `OPENROIS_MCP_PORT` | `127.0.0.1`, 8000 | Where streamable-http listens |

## Not in This Version

- One tool per component command, generated from the profiles.
- Authentication and several users on one streamable-http server, which wait for
  authentication at the gateway.
- Audio and video streams, which wait for media in the SDK.
- Several gateways from one server.

## Tests

```bash
pip install -e ../../interfaces/python -e ../../sdk/python -e ".[dev]"
pytest                                                  # unit tests
OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 pytest         # also against the compose stack
mypy
ruff check src/ tests/
```

## License

Apache-2.0. See [LICENSE](LICENSE).
