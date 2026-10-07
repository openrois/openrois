# Mock Adapter

A working adapter that needs no robot. It connects to a gateway, registers four
components (`SystemInformation`, `Navigation`, `ObjectDetection`, and
`ObjectManipulation`), answers with hardcoded data, and fires events on a timer to
simulate activity.

Use it to develop clients and to exercise a gateway end to end.

## Run With Docker Compose

From the repository root, start a gateway with the mock adapter behind it:

```bash
docker compose up --build
python gateway/scripts/smoke.py    # needs pip install websockets
```

The gateway listens on `ws://127.0.0.1:8765`. The smoke script connects as a client, waits
until the adapter's components appear, runs a query, and waits for an event.

## Run Without Docker

```bash
# From the repository root. The packages are not published yet.
pip install -e ./interfaces/python -e ./components/core -e ./engine -e ./gateway

# Terminal 1: the gateway, on ws://127.0.0.1:8765.
openrois-gateway

# Terminal 2: the adapter.
cd examples/mock-adapter
python mock_adapter.py --config openrois-profile.yaml
```

`OPENROIS_GATEWAY_URL`, when set, overrides the gateway URL in the profile.

The [HRI client](../hri-client/README.md) reaches this setup once the engine moves to the
RoIS method catalog (in progress).

## What It Simulates

| Component | Behavior |
|-----------|----------|
| `SystemInformation` | Fixed position and battery level |
| `Navigation` | Accepts a target and reports `BUSY`. Fires `reached_target` 5 seconds after a subscription |
| `ObjectDetection` | Lists two detected objects, fires `object_detected` 3 seconds after a subscription |
| `ObjectManipulation` | Reports gripper state. Fires `manipulation_complete` 4 seconds after a subscription |

## Read It as a Template

`mock_adapter.py` is a single file that shows the whole adapter shape: decorated component
classes, `meta_from_decorators`, `Engine.register_component`, and `WsClient`. To start your
own, copy [`examples/adapter-template`](../adapter-template/README.md) instead, which has
the same structure with the bodies left blank.
