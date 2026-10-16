# openrois-engine

The recursive RoIS HRI Engine, with its WebSocket server and client.

One `Engine` class realizes both roles the specification defines. Give it child engines and
it is a **main HRI Engine**, the gateway that applications connect to. Give it local
components and it is a **sub HRI Engine**, the adapter that runs next to a robot. Give it
both and it is a middle tier, which is how OpenRoIS composes into a hierarchy without a
second implementation.

The engine answers the RoIS method catalog of
[`openrois-interfaces`](../interfaces/python/README.md), the same 16 methods and 4
notifications at every level. A parent engine reaches a child engine with the requests a
client would send.

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python -e ./engine
```

Components are written with [`openrois-components-core`](../components/core/README.md):

```bash
pip install -e ./components/core
```

## Public API

| Name | Purpose |
|------|---------|
| `Engine` | The recursive HRI Engine: the method catalog, bindings, command sequences and id routing |
| `Session` | A client of an engine, or its parent engine |
| `ComponentContract` | Where the components of an engine live, local or behind a child engine |
| `LocalComponent` | The shape of a component the engine hosts in its process, which `Component` has |
| `LocalComponents` | The contract for the components of this process: parameters, commands, status and events |
| `ChildEngine` | The contract for one child engine, reached over the method catalog |
| `WsServer` | WebSocket server, for a gateway |
| `WsClient` | WebSocket client, for an adapter connecting out to a gateway |

The configuration loader lives in `openrois.engine.config`:

| Name | Purpose |
|------|---------|
| `AdapterConfig` | The settings every adapter has, subclassed with one section per component |
| `load_adapter_config` | Load an adapter's settings from `adapter.yaml`, the environment and flags |
| `load_config` | The loader behind it, generic over the model and the environment prefix, which the gateway uses too |
| `ConfigError` | Raised for a file that cannot be read or settings that do not validate |

## Usage

As an adapter, with a component written with `openrois-components-core`:

```python
from pydantic import BaseModel

from openrois.engine import Engine, WsClient
from openrois.engine.config import AdapterConfig, load_adapter_config


class NavigationSettings(BaseModel):
    speed: float = 0.5


class RobotConfig(AdapterConfig):
    engine_id: str = "robot_1"
    navigation: NavigationSettings = NavigationSettings()


config = load_adapter_config(RobotConfig)
engine = Engine(config.engine_id)
engine.add_component("navigation", Navigation(config.robot_address, config.navigation))
WsClient(engine, config.gateway_url).run()
```

The component is served as `robot_1/navigation`. `WsClient` opens the resources the
components share, connects the components to their backends, serves the gateway until
Ctrl+C, and then disconnects them and closes the resources.

`load_adapter_config` reads the settings in four layers, each overriding the one before:
the defaults of the model, the YAML file named by `--config` or `OPENROIS_ADAPTER_CONFIG`,
the environment, and the flags. The file is `adapter.yaml` by convention, never a
profile, because a profile is what `rois.system.get_profile` returns:

```yaml
gateway_url: ws://gateway.example.com:8765
engine_id: robot_1
robot_address: http://192.168.0.10:8080
log_level: info
navigation:
  speed: 0.8
```

The environment and the flags set only the four settings every adapter has:

| Setting | Flag | Environment | Default |
|---------|------|-------------|---------|
| `gateway_url` | `--gateway-url` | `OPENROIS_ADAPTER_GATEWAY_URL` | `ws://127.0.0.1:8765` |
| `engine_id` | `--engine-id` | `OPENROIS_ADAPTER_ENGINE_ID` | none, the subclass gives one |
| `robot_address` | `--robot-address` | `OPENROIS_ADAPTER_ROBOT_ADDRESS` | none |
| `log_level` | `--log-level` | `OPENROIS_ADAPTER_LOG_LEVEL` | `info` |

The component sections come from the file only. A ROS 2 adapter shares one
`RclpyExecutor`, from `openrois.components.core.ros2`, among its components. It is a
resource, so the engine opens it before the components connect and closes it after they
disconnect.

As a gateway:

```python
import asyncio

from openrois.engine import Engine, WsServer


async def main() -> None:
    engine = Engine("gateway")
    server = WsServer(engine)
    await engine.start()
    # Loopback only by default: the server does not authenticate its peers.
    await server.start("127.0.0.1", 8765)
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()
        await engine.stop()


asyncio.run(main())
```

The standalone gateway process, `openrois-gateway` in [`gateway/`](../gateway/README.md),
runs exactly this with configuration and signal handling.

## What the Engine Does

- **Sessions.** A session sends `rois.system.connect` before anything else, and every
  other request before it, or after `disconnect`, is answered with ERROR. `disconnect`,
  or a connection that closes, releases the binds and subscriptions of the session and
  aborts every sequence it had running.
- **Refs and ids.** Every ref is `engine_id/name`, owned by the engine that hosts the
  component. The ids an engine assigns, for commands, subscriptions, events, errors and
  set_parameter commands, start with its engine id too, so every engine in the hierarchy
  routes them back to their owner, and a service application or an agent can tell where
  each one came from. Engine ids are unique across the hierarchy. The engine a client
  calls assigns every command id of an `execute` and returns the sequence with them, and
  the engines below reuse them.
- **Conditions.** search, bind_any, get_profile, query and subscribe select components
  with the CQL2-Text subset of `openrois.interfaces.condition`. get_profile lists the
  child engines as sub profiles, trimmed to the components a condition selects. The
  condition of a query or a subscribe also gives the arguments of its message, for
  example `stream_id = 'audio-1'`.
- **Binds.** `execute`, `get_parameter` and `set_parameter` need a bind from the calling
  session on every component they name, and answer ERROR without it. An actuation
  component takes one bind at a time, and a second session gets OUT_OF_RESOURCES. Any
  other component, one declared without a RoSO function included, takes one bind per
  session. `release` drops the caller's bind and aborts its commands still running on
  the component. A parent engine checked the binds before it forwarded a request, so the
  session of a parent is trusted. Clients therefore connect to the top engine of a
  hierarchy, which holds the binds for every engine below it. To abort a command on a
  child engine, the parent sends it a `stop` of the component and then a `release`, but
  only when no other client of the parent still holds the component.
- **execute.** The engine checks the whole sequence before it answers: UNSUPPORTED for a
  command no component serves, ERROR for a component the session has not bound, and
  BAD_PARAMETER for arguments that do not fit the profile. It then runs the items in
  order, waits each `delay_time`, and runs the branches of a `ConcurrentCommands` item at
  the same time, each branch in order and each command after its own `delay_time`. Each
  engine sends a child one command at a time, with the delay already waited. A command
  that ends other than OK stops its branch and the items after it, whose commands
  complete with ABORT. Every command sends one `rois.command.completed`, to the session
  that started it.
- **Parameters.** `set_parameter` applies the values before it replies and then sends
  `rois.command.completed`. A parameter the profile marks `read_only`, one it does not
  list, a value that does not fit its type, or values the component's
  `@on_set_parameter` hook refuses answer BAD_PARAMETER with no command id, and none of
  the values is applied. Inside `execute`, a hook refusal ends that command with ERROR.
- **Status and errors.** The engine answers `component_status` for the asking session:
  BUSY when another session holds an actuation component, UNINITIALIZED until the
  component's resources are open and it has connected, and WARNING or ERROR as the
  component or one of its resources raised it, ERROR above WARNING above the lifecycle.
  Each raise that changes what a component reports sends `rois.system.notify_error` to
  the sessions with a bind or a subscription on it, and `get_error_detail` reads its
  `component_ref`, `status`, `message` and `time` until it clears. A raised ERROR refuses
  the component's commands and queries and holds back its events. `Engine.raise_status`
  reports an error of the engine itself to every connected session.
- **Local components.** The engine opens the resources the components share, stores the
  parameters, filled from the profile defaults, and answers `get_parameter` itself. A
  command not started within the timeout of its profile ends with TIMEOUT. A `stop`, or
  a new `start`, runs the `stop` handler and then aborts the running `start`. Events can
  be emitted from any thread, and `get_event_detail` reads an event until it expires. An
  event an emit names argument values for reaches the subscriptions that asked for them.
- **RoIS_Common.** A local component whose profile includes RoISCommon gets `start`,
  `stop`, `suspend` and `resume` by default. It is started from the moment a `start`
  arrives until `stop`, or until that start ends other than OK, and a `start` without a
  handler completes OK at once. On a component not started, `suspend`, `resume` and
  `stop` complete OK and run no handler, except that a `stop` while a cancelled `start`
  still unwinds cancels it again. `suspend` holds `start` and every other function
  command of the component, which wait without starting, directly or in a sequence, and
  end with TIMEOUT when their profile timeout elapses. `set_parameter` still applies at
  once, a command already running keeps running, and the component's events are dropped
  until `resume`, which releases the held commands. `stop` ends the suspension, and the
  held commands end with ABORT. A handler adds to this: the `suspend` handler runs after
  the hold, and the `resume` handler before the release. A `suspend` that fails lifts its
  hold, and a `resume` that fails keeps it. `component_status` does not change while a
  component is suspended. A gateway forwards the four commands and holds nothing itself.

## Transport

`WsServer` serves child engines and clients on one port:

- A connection on the path `/adapter` is a child engine. The server connects to it with
  `rois.system.connect`, reads its profile with `rois.system.get_profile` and adds it to
  the engine. A child whose profile names an
  empty or slashed engine id, an engine id already in the hierarchy, or a ref no engine of
  the child owns, is closed with code 1008 and the reason. A child that sends
  `rois.system.profile_changed` is read again, and a changed profile that breaks these
  rules closes the child the same way. A reply that assigns an id outside the child's
  engine ids, or one the child already gave out, counts as ERROR.
- A connection on any other path is a client with its own session. When it disconnects,
  its binds and subscriptions are released and its sequences aborted.
- Each request runs in its own task, so a slow request does not hold up the others, and
  replies are matched to requests by id. A reply always goes out before the notifications
  it causes, such as the completion of a set_parameter.
- A message that is not JSON gets PARSE_ERROR, one that is not a JSON-RPC request gets
  INVALID_REQUEST, a method outside the catalog gets METHOD_NOT_FOUND, params that fail
  the catalog model get INVALID_PARAMS with the issues as data, and an engine failure
  gets INTERNAL_ERROR. A notification gets no reply.
- `child_timeout` sets how long the server waits for a child engine's reply, 10 seconds by
  default. A request that times out may still take effect on the child: a subscription
  whose reply comes too late is ended, while a command keeps running. `stop()` closes
  every connection with code 1001.

`WsClient` appends `/adapter` to the gateway URL, serves the gateway through a trusted
session, and reconnects with a growing delay, also when the gateway refuses it.

## Design Constraints

- The engine is transport-neutral and paradigm-neutral. It reaches every component
  through the `ComponentContract`, so no ROS, DDS, gRPC, or game engine import belongs in
  this package. ROS 2 nodes are spun by `RclpyExecutor` in `openrois-components-core`,
  a resource the components share.
- Components own their backend connections. The engine holds no shared backend state.

See [architecture](https://openrois.org/docs/concepts/architecture) and
[the recursive engine](https://openrois.org/docs/concepts/recursive-engine) for the
rationale.

## Test

```bash
pip install -e ./interfaces/python -e ./components/core -e "./engine[dev]"
cd engine && pytest && mypy && ruff check src/ tests/
```

The tests drive the engine through the JSON-RPC framing in process, and run a real
`WsServer` on an ephemeral loopback port with adapters, clients and a middle tier
connected over WebSockets.

## Status

Alpha, pre-1.0, unstable API. The engine implements the RoIS interfaces, profiles and
common messages (CP1 to CP3) as
[rois-reference §16](../docs/rois-reference.md#16-known-normative-divergences) records
them, without a conformance claim. It does not yet load XML-declared profiles at run time.
Re-subscription after an adapter reconnects and health endpoints are planned for [Phase 5](https://openrois.org/docs/project/roadmap).

## License

Apache-2.0.
