# Mock Adapter

A working adapter that needs no robot. It connects to a gateway, registers four
components (`SystemInformation`, `Navigation`, `ObjectDetection`, and
`ObjectManipulation`), answers with hardcoded data, and fires events on a timer to
simulate activity.

Use it to develop clients and to exercise a gateway end to end.

## Install

```bash
# From the repository root. The packages are not published yet.
pip install -e ./interfaces/python
pip install -e ./components/core
pip install -e ./core
```

## Run

```bash
# 1. Start a gateway that accepts adapter registrations on ws://127.0.0.1:8765.
# 2. Then, in another terminal:
python mock_adapter.py --config openrois-profile.yaml
```

Point [`examples/hri-client`](../hri-client/README.md) at the gateway to see the four
components appear, run their queries, and subscribe to their events.

## What It Simulates

| Component | Behavior |
|-----------|----------|
| `SystemInformation` | Fixed position and battery level |
| `Navigation` | Accepts a target, reports `BUSY`, then fires `reached_target` and completes the command after 5 seconds |
| `ObjectDetection` | Lists two detected objects, fires `object_detected` 3 seconds after a subscription |
| `ObjectManipulation` | Reports gripper state, fires `manipulation_complete` and completes the command 4 seconds after `execute` |

## Read It as a Template

`mock_adapter.py` is a single file that shows the whole adapter shape: decorated component
classes, `meta_from_decorators`, `Engine.register_component`, and `WsClient`. To start your
own, copy [`examples/adapter-template`](../adapter-template/README.md) instead, which has
the same structure with the bodies left blank.
