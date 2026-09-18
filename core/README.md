# openrois-core

The recursive RoIS HRI Engine, with its WebSocket server and client.

One `Engine` class realizes both roles the specification defines. Give it child engines and
it is a **main HRI Engine**, the gateway that applications connect to. Give it local
components and it is a **sub HRI Engine**, the adapter that runs next to a robot. Give it
both and it is both, which is how OpenRoIS composes into a hierarchy without a second
implementation.

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python
pip install -e ./core
```

## Public API

| Name | Purpose |
|------|---------|
| `Engine` | The recursive HRI Engine: routing, profile aggregation, bind and release |
| `ComponentRegistry` | Local components, the in-process side of the Component Contract |
| `SubEngine` | A remote child engine, the WebSocket side of the Component Contract |
| `EventEmitter` | Delivers events to subscribers |
| `WsServer` | WebSocket server, for a gateway |
| `WsClient` | WebSocket client, for an adapter connecting out to a gateway |
| `openrois_core.gateway` | The gateway process: `serve()` and the `openrois-gateway` command |
| `read_profile`, `component_config` | Load a profile YAML file and slice per-component configuration out of it |

## Usage

As a gateway, from the command line (also `python -m openrois_core.gateway`, and
`docker compose up` at the repository root):

```bash
openrois-gateway --host 0.0.0.0 --port 8765
```

The same composition in code:

```python
import asyncio

from openrois_core import Engine, WsServer


async def main() -> None:
    server = WsServer(Engine(engine_id="gateway", platform="", enforce_bindings=True))
    await server.start("0.0.0.0", 8765)
    # start() returns once the server is listening, so keep the loop alive.
    await asyncio.Event().wait()


asyncio.run(main())
```

As an adapter:

```python
from openrois_core import Engine, WsClient, component_config, read_profile
from openrois_components_core import meta_from_decorators

profile = read_profile("openrois-profile.yaml")
engine = Engine(engine_id=profile["engine"]["id"], platform=profile["engine"]["platform"])

meta = meta_from_decorators(Navigation)
engine.register_component(meta.ref, Navigation(component_config(profile, meta.ref)), meta)

WsClient(engine, profile["engine"]["gateway_url"]).run()
```

## Design Constraints

- The engine is transport-neutral and paradigm-neutral. It reaches everything through the
  five-method `ComponentContract` (`discover`, `invoke`, `query`, `subscribe`,
  `unsubscribe`), so no ROS, DDS, gRPC, or game engine import belongs in this package.
- Components own their backend connections. The engine holds no shared backend state.

See [architecture](https://openrois.org/docs/concepts/architecture) and
[the recursive engine](https://openrois.org/docs/concepts/recursive-engine) for the
rationale.

## Status

Alpha, pre-1.0, unstable API. A regression test suite covers dispatch, bindings, events,
and a gateway plus adapter round trip (`pytest` in this directory). Hardening, graceful
shutdown, and reconnection are [Phase 5](https://openrois.org/docs/project/roadmap).

## License

Apache-2.0.
