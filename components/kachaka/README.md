# openrois-components-kachaka

OpenRoIS components for the [Preferred Robotics Kachaka](https://kachaka.life/). They
implement the basic RoIS components Navigation and SystemInformation, and translate RoIS
messages into Kachaka calls, over either the gRPC API or ROS 2.

| Component | Backend | Serves |
|-----------|---------|--------|
| `GrpcNavigation` | gRPC API | `start`, `stop`, `component_status`, the `reached_target` event, and the Navigation parameters |
| `Ros2Navigation` | ROS 2 | The same messages, over the `ExecKachakaCommand` action and the location list topic |
| `GrpcSystemInformation` | gRPC API | `robot_position`, `engine_status` |
| `Ros2SystemInformation` | ROS 2 | The same queries, from the odometry topic |

Two backends for one RoIS component type is the point: both classes declare the same
profile constant, so a client sees `Navigation` either way and does not know which one
runs.

`start` drives to the first of `target_positions`, a location of the Kachaka named by its
name or its id, and runs until the Kachaka gets there. Then the component emits
`reached_target`, and the engine completes the command with OK. An unknown location or a
failed drive ends the command with ERROR. `stop`, or a new `start`, cancels the drive,
which ends with ABORT. The engine stores `time_limit` and `routing_policy`, and the
components do not apply them to the Kachaka.

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python -e ./engine -e ./components/core
pip install -e "./components/kachaka[grpc]"    # the gRPC API backend
pip install -e ./components/kachaka            # the ROS 2 backend
```

The ROS 2 backend needs a sourced ROS 2 installation with `rclpy`, `nav_msgs` and the
`kachaka_interfaces` package.

## Usage

```python
from openrois.components.kachaka import GrpcNavigation, GrpcSystemInformation
from openrois.engine import Engine, WsClient

kachaka = "192.168.1.100:26400"
engine = Engine("kachaka_1")
engine.add_component("navigation", GrpcNavigation(kachaka))
engine.add_component("system_information", GrpcSystemInformation(kachaka))
WsClient(engine, "ws://127.0.0.1:8765").run()
```

Clients see `kachaka_1/navigation` and `kachaka_1/system_information`. For ROS 2, use
`Ros2Navigation()` and `Ros2SystemInformation()`, whose keyword arguments name the node
and the topics. `WsClient` spins their rclpy nodes in a background thread.

## Test

```bash
pip install -e ./interfaces/python -e ./engine -e ./components/core \
    -e "./components/kachaka[dev]"
cd components/kachaka && pytest && mypy && ruff check src/ tests/
```

The tests run the components in an engine against stand-ins for the gRPC API, rclpy and
the Kachaka interfaces, so they need neither a Kachaka nor ROS 2. A Kachaka is the only
full check.

## License

Apache-2.0.
