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

## Usage

As an adapter, with a component written with `openrois-components-core`:

```python
from openrois.engine import Engine, WsClient

engine = Engine("robot_1")
engine.add_component("navigation", Navigation("http://192.168.0.10:8080"))
WsClient(engine, "ws://gateway.example.com:8765").run()
```

The component is served as `robot_1/navigation`. `WsClient` connects the components to
their backends, serves the gateway until Ctrl+C, and disconnects them.

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

- **Refs and ids.** Every ref is `engine_id/name`, owned by the engine that hosts the
  component. The ids an engine assigns, for subscriptions, events and set_parameter
  commands, start with its engine id too, so every engine in the hierarchy routes them
  back to their owner, and a service application or an agent can tell where each one
  came from. Engine ids are unique across the hierarchy.
- **Conditions.** search, bind_any, get_profile, query and subscribe select components
  with the CQL2-Text subset of `openrois.interfaces.condition`. get_profile lists the
  child engines as sub profiles, trimmed to the components a condition selects.
- **Bindings.** Only actuation components are reserved. A command or a set_parameter on
  an actuation component needs the binding of the session that sends it. A parent engine
  checked the bindings before it forwarded a request, so the session of a parent is
  trusted. Clients therefore connect to the top engine of a hierarchy, which holds the
  bindings for every engine below it.
- **execute.** The engine checks the whole sequence before it answers: UNSUPPORTED for a
  command no component serves, OUT_OF_RESOURCES for a missing binding, BAD_PARAMETER for
  arguments that do not fit the profile, and for a command id that is empty, reused, or
  starts with the id of an engine and a slash. It then runs the items in order, waits
  each `delay_time`, and runs the commands of a `ConcurrentCommands` item at the same
  time, each after its own `delay_time`. Each engine sends a child one command at a
  time, with the delay already waited. A command that ends other than OK stops the
  sequence, and the commands after it complete with ABORT. Every command sends one
  `rois.command.completed`, to the session that started it.
- **Local components.** The engine stores the parameters, filled from the profile
  defaults, and answers `get_parameter` and `component_status` itself: UNINITIALIZED
  until the component has connected, ERROR when `connect()` failed, BUSY while a command
  runs, READY otherwise. A command ends with TIMEOUT past the timeout of its profile. A
  `stop`, or a new `start`, runs the `stop` handler and then aborts the running `start`.
  Events can be emitted from any thread, and `get_event_detail` reads an event until it
  expires.

## Transport

`WsServer` serves child engines and clients on one port:

- A connection on the path `/adapter` is a child engine. The server reads its profile
  with `rois.system.get_profile` and adds it to the engine. A child whose profile names an
  empty or slashed engine id, an engine id already in the hierarchy, or a ref no engine of
  the child owns, is closed with code 1008 and the reason. A child that sends
  `rois.system.profile_changed` is read again, and a changed profile that breaks these
  rules closes the child the same way. A reply that assigns an id outside the child's
  engine ids, or one the child already gave out, counts as ERROR.
- A connection on any other path is a client with its own session. When it disconnects,
  its bindings and subscriptions are released.
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
  this package. `WsClient` spins the rclpy node a component keeps in `_node` when rclpy is
  installed, without importing it otherwise.
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

Alpha, pre-1.0, unstable API. Re-subscription after an adapter reconnects and health
endpoints are planned for [Phase 5](https://openrois.org/docs/project/roadmap).

## License

Apache-2.0.
