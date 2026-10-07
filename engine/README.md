# openrois-engine

The recursive RoIS HRI Engine, with its WebSocket server and client.

One `Engine` class realizes both roles the specification defines. Give it child engines and
it is a **main HRI Engine**, the gateway that applications connect to. Give it local
components and it is a **sub HRI Engine**, the adapter that runs next to a robot. Give it
both and it is both, which is how OpenRoIS composes into a hierarchy without a second
implementation.

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python -e ./engine
```

## Public API

| Name | Purpose |
|------|---------|
| `Engine` | The recursive HRI Engine: routing, profile aggregation, bind and release |
| `ComponentRegistry` | Local components, the in-process side of the Component Contract |
| `ChildEngineProxy` | The gateway's stand-in for one connected child engine (an adapter or a lower gateway), the WebSocket side of the Component Contract |
| `EventEmitter` | Delivers events to subscribers |
| `WsServer` | WebSocket server, for a gateway |
| `WsClient` | WebSocket client, for an adapter connecting out to a gateway |
| `read_profile`, `component_config` | Load a profile YAML file and slice per-component configuration out of it |

## Usage

As a gateway:

```python
import asyncio

from openrois.engine import Engine, WsServer


async def main() -> None:
    server = WsServer(Engine(engine_id="gateway", enforce_bindings=True))
    # Loopback only by default: the server does not authenticate its peers.
    await server.start("127.0.0.1", 8765)
    try:
        # start() returns once the server is listening, so keep the loop alive.
        await asyncio.Event().wait()
    finally:
        await server.stop()


asyncio.run(main())
```

A standalone gateway process, `openrois-gateway`, is in progress in `gateway/`.

As an adapter:

```python
from openrois.engine import Engine, WsClient, component_config, read_profile
from openrois_components_core import meta_from_decorators

profile = read_profile("openrois-profile.yaml")
engine = Engine(engine_id=profile["engine"]["id"], platform=profile["engine"]["platform"])

meta = meta_from_decorators(Navigation)
engine.register_component(meta.ref, Navigation(component_config(profile, meta.ref)), meta)

WsClient(engine, profile["engine"]["gateway_url"]).run()
```

## Transport

`WsServer` serves child engines and clients on one port:

- A connection on the path `/adapter` is a child engine. The server asks it for its
  components with `rois.command.search` and registers it under the engine id it reports.
  An empty engine id, one with a slash, or one already connected closes the connection with
  code 1008 and the reason.
- A connection on any other path is a client. Each request runs in its own task, so a slow
  command does not hold up the others, and replies are matched to requests by id.
- Events from a child engine go to the client that subscribed. When a client disconnects,
  its bindings and subscriptions are released.
- A message that is not JSON gets PARSE_ERROR, one that is not a JSON-RPC request gets
  INVALID_REQUEST, positional params get INVALID_PARAMS, and an engine failure gets
  INTERNAL_ERROR. A notification gets no reply.
- `child_timeout` sets how long the server waits for a child engine's reply, 10 seconds by
  default. `stop()` closes every connection with code 1001.

`WsClient` appends `/adapter` to the gateway URL, answers each request in its own task, and
reconnects with exponential backoff.

## Design Constraints

- The engine is transport-neutral and paradigm-neutral. It reaches everything through the
  five-method `ComponentContract` (`discover`, `invoke`, `query`, `subscribe`,
  `unsubscribe`), so no ROS, DDS, gRPC, or game engine import belongs in this package.
- Components own their backend connections. The engine holds no shared backend state.

See [architecture](https://openrois.org/docs/concepts/architecture) and
[the recursive engine](https://openrois.org/docs/concepts/recursive-engine) for the
rationale.

## Test

```bash
pip install -e ./interfaces/python -e ./components/core -e "./engine[dev]"
cd engine && pytest && ruff check src/ tests/
```

The tests run a real `WsServer` on an ephemeral loopback port, with adapters and clients
connected over WebSockets.

## Status

Alpha, pre-1.0, unstable API. The move to the RoIS method catalog of
`openrois-interfaces` is in progress. Re-subscription after an adapter reconnects and health
endpoints are planned for [Phase 5](https://openrois.org/docs/project/roadmap).

## License

Apache-2.0.
