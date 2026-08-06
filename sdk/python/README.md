# openrois-adapter-sdk

Python SDK for building OpenRoIS adapters.

## Install

```bash
pip install openrois-adapter-sdk
```

## Quick start

1. Write a config file (e.g., `openrois-profile.yaml`):

```yaml
fleet_id: robot_1
connection:
  ws:
    host: "127.0.0.1"
    port: 8765
components:
  - ref: "SystemInformation"
    type: basic
    bind_required: false
    queries: [robot_position, component_status]
```

2. Write an adapter:

```python
from openrois.sdk import RobotAdapter, component, query, results

class MyAdapter(RobotAdapter):
    @component("SystemInformation", bind_required=False)
    class SystemInformation:
        @query("robot_position")
        async def robot_position(self):
            return results.position(x=3.2, y=1.8, theta=0.5)
```

3. Run (framework coming in days 4-5):

```bash
python my_adapter.py --config openrois-profile.yaml
```
