# openrois-Components-Kachaka

OpenRoIS components for the [Preferred Robotics Kachaka](https://kachaka.life/). They
implement canonical RoIS components and translate RoIS messages into Kachaka calls, over
either the gRPC API or ROS 2.

| Component | Backend | Provides |
|-----------|---------|----------|
| `GrpcNavigation` | gRPC API | `set_parameter` and `get_parameter` for the target, `start`, `stop`, `component_status`, and the `reached_target` event |
| `Ros2Navigation` | ROS 2 | The same messages, over ROS 2 topics and actions |
| `GrpcSystemInformation` | gRPC API | `robot_position`, `engine_status`, `component_status` |
| `Ros2SystemInformation` | ROS 2 | The same messages, over ROS 2 |

Two backends for one RoIS component is the point: the application above the gateway sees
`Navigation` either way and does not know which one is running.

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python
pip install -e ./components/core
pip install -e "./components/kachaka[api]"     # gRPC API backend
pip install -e "./components/kachaka[ros2]"    # ROS 2 backend
```

The ROS 2 backend additionally needs a sourced ROS 2 installation with `rclpy`.

## Usage

```python
from openrois_components.kachaka import GrpcNavigation
from openrois_components_core import meta_from_decorators
from openrois_core import Engine, WsClient, component_config, read_profile

profile = read_profile("openrois-profile.yaml")
engine = Engine(engine_id=profile["engine"]["id"], platform="kachaka")

meta = meta_from_decorators(GrpcNavigation)
engine.register_component(meta.ref, GrpcNavigation(component_config(profile, meta.ref)), meta)

WsClient(engine, profile["engine"]["gateway_url"]).run()
```

The component reads its backend address from the `components` section of the adapter
profile, so the same code runs against any Kachaka on the network.

```yaml title="openrois-profile.yaml"
engine:
  id: kachaka_1
  platform: kachaka
  gateway_url: "ws://127.0.0.1:8765"

components:
  Navigation:
    grpc_server: "192.168.1.100:26400"
    auto_homing: false
    poll_interval: 0.5
```

See [`examples/adapter-template`](../../examples/adapter-template/README.md) for the full
adapter shape.

## License

Apache-2.0.
