# Adapter Template

A starting point for connecting your own robot, avatar, or service to OpenRoIS.

An adapter is a sub HRI Engine: it hosts an `Engine` with the components it implements,
and connects out to a gateway with `WsClient`. The gateway then presents your platform to
every RoIS client through the same standard interfaces as any other.

## Install

The Python packages are not published yet, so install them from a clone of the
repository:

```bash
pip install -e ./interfaces/python -e ./engine -e ./components/core
```

## Use the Template

1. Copy this directory onto a machine that can reach the API of your platform.

2. Edit `my_adapter.py`. Each component keeps its RoIS logic in its handlers and its calls
   to your platform in private methods marked `IMPLEMENT YOUR CODE HERE`. Replace each
   `NotImplementedError` with a call to the API of your platform (ROS 2 topics and
   actions, HTTP, gRPC, serial):

   ```python
   async def _read_pose(self) -> tuple[float, float, float]:
       pose = await self._api.get_pose()
       return pose.x, pose.y, pose.theta
   ```

3. Start a gateway, then run the adapter:

   ```bash
   python my_adapter.py --robot-url http://192.168.0.10:8080 --engine-id my_robot
   ```

   `--gateway-url` defaults to `OPENROIS_GATEWAY_URL`, or `ws://127.0.0.1:8765`.

The adapter connects to the gateway, which reads its profile and lists `my_robot/navigation`,
`my_robot/system_information` and `my_robot/battery`. Verify it with
[`examples/hri-client`](../hri-client/README.md), which shows every component with its
queries, commands and events.

## The Three Components

| Component | Type | What it shows |
|-----------|------|---------------|
| `MyNavigation` | `OMG::Navigation`, declared with `NAVIGATION_PROFILE` | A basic type implemented in part: `start` and `stop`, the `reached_target` event, and `CommandFailed` for a command that cannot run |
| `MySystemInformation` | `OMG::SystemInformation`, declared with `SYSTEM_INFORMATION_PROFILE` | A basic type with queries only |
| `Battery` | `MyOrganization::Battery`, declared with its own `BATTERY_PROFILE` | A type of your own, with a query, an event emitted by a monitor that the first subscription starts, and a parameter |

The engine does the rest for every component: it stores the parameters from the profile
defaults, answers `component_status`, reserves actuation components for the client that
binds them, reports the end of each command with `rois.command.completed`, and serves the
part of each profile the class implements. Components own their backend connections:
open them in `connect()`, close them in `disconnect()`.

See [`components/core`](../../components/core/README.md) for the decorators and
[`examples/mock-adapter`](../mock-adapter/README.md) for an adapter that runs as is.

## Keep It Conformant

Use the basic RoIS component types where one fits, through their profile constants in
`openrois.interfaces.components`. A component type of your own is valid RoIS (section 12
of the specification): give it an authority of your own and declare every message in its
profile, so applications discover it the way they discover the basic types. See
[components and adapters](https://openrois.org/docs/guides/components-and-adapters) and
the [component reference](https://openrois.org/docs/reference/components).
