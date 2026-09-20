# gateway (Python)

Minimal OpenRoIS gateway process: composes `Engine` + `WsServer` from
`openrois_core`. This is the Python counterpart of the TypeScript
gateway in `gateway/` and a preview of roadmap Phase 6.

The gateway has no local components. Adapters connect on the
`/adapter` path and are discovered via `rois.command.search`. Clients
connect on any other path and send RoIS operations.

## Run

```bash
pip install -e ../../core
python gateway.py [--host HOST] [--port PORT]
```

Defaults: host `0.0.0.0` (or `ENGINE_HOST`), port `8765`
(or `ENGINE_PORT`).

## Test with the RealSense adapter

```bash
# Terminal 1: gateway
python gateway.py

# Terminal 2: adapter (ROS 2 environment sourced)
cd ../realsense-adapter
python realsense_adapter.py --config openrois-profile.yaml
```

Then connect a client (e.g. `examples/hri-client`) to
`ws://localhost:8765`, or use the Python SDK.