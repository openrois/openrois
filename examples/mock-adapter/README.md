# Mock Adapter

A working adapter that needs no robot. It hosts the three components of the
[TypeScript mock engine](../mock-engine/README.md) on the Python engine, under the engine id
`mock`, and serves them to a gateway. Each component is declared with the profile constant
of its type, so a client sees the same refs, profiles, parameters, events and timing
whichever of the two it talks to.

Use it to develop clients and to exercise a gateway end to end.

| Ref | Profile | Function | Behavior |
|-----|---------|----------|----------|
| `mock/person_detection` | `OMG::PersonDetection` | sensing | Emits `person_detected` every five seconds, counting zero to three persons in turn |
| `mock/navigation` | `OMG::Navigation` | actuation | `start` drives to the first of `target_positions` for three seconds, reports `BUSY`, then emits `reached_target` |
| `mock/system_information` | `OMG::SystemInformation` | | Answers `robot_position` with the robot at the origin, and `engine_status` |

The person detection and navigation components take the RoIS_Common commands (`start`,
`stop`, `suspend`, `resume`), which take 0.2 seconds unless the table says otherwise. The
engine answers `component_status` for them. Navigation starts with `target_positions` set to
`["home"]`, a default that `Navigation.xml` leaves empty, so a client can start it before
setting any parameter. A `stop`, or a new `start`, ends a running drive with `ABORT`.

## Run With Docker Compose

From the repository root, start a gateway with the mock adapter behind it:

```bash
docker compose up --build
python gateway/scripts/smoke.py    # needs pip install websockets
```

The gateway listens on `ws://127.0.0.1:8765`. The smoke script connects as a client, waits
until the adapter's components appear, runs the queries, reads an event, and drives the
navigation to a target. `OPENROIS_MOCK_TIME_SCALE=0.1 docker compose up --build` makes the
simulated work ten times faster.

## Run Without Docker

```bash
# From the repository root. The packages are not published yet.
pip install -e ./interfaces/python -e ./engine -e ./components/core -e ./components/common \
    -e ./gateway

# Terminal 1: the gateway, on ws://127.0.0.1:8765.
openrois-gateway

# Terminal 2: the adapter.
python examples/mock-adapter/mock_adapter.py
```

| Setting | Flag | Environment | Default |
|---------|------|-------------|---------|
| Gateway URL | `--gateway-url` | `OPENROIS_GATEWAY_URL` | `ws://127.0.0.1:8765` |
| Engine id, the first part of every ref | `--engine-id` | `OPENROIS_MOCK_ENGINE_ID` | `mock` |
| Factor on every delay | | `OPENROIS_MOCK_TIME_SCALE` | `1` |
| Log level | `--log-level` | | `info` |

## Read It as an Example

`mock_adapter.py` is a single file that shows the whole adapter shape: components written
with [`openrois-components-core`](../../components/core/README.md), one of them reused from
[`openrois-components-common`](../../components/common/README.md), hosted with
`Engine.add_component` and served with `WsClient`. To start an adapter of your own, copy
[`examples/adapter-template`](../adapter-template/README.md).
