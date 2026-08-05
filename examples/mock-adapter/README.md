# Mock Adapter

A working mock adapter for testing the OpenRoIS adapter SDK without a
real robot. Connects to the avatar, registers 4 components, and responds
with hardcoded data.

## Usage

1. Start the avatar app (or any WS server that accepts adapter
   registration on the configured port).

2. Run the mock adapter:

```bash
python mock_adapter.py --config profile.yaml
```

3. From an operator SDK, call `search()`, `query()`, `execute()`, and
   `subscribe()` to verify the full flow.

The mock adapter fires a `reached_target` event 5 seconds after a
subscribe request, and an `object_detected` event 3 seconds after
subscribing to object detection.