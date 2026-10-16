# openrois-components-core

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)

The OpenRoIS component SDK: write a RoIS HRI Component as a Python class. A component
declares the RoIS type it implements, marks the messages it supports, and talks to its
robot, avatar or AI service in its own code. The engine that hosts it stores its
parameters, answers `component_status`, tracks its commands and serves the part of the
profile it implements.

This is what an adapter author imports. It has no transport and no robot in it, and it
depends on [`openrois-interfaces`](../../interfaces/python/README.md) only.

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python -e ./components/core
```

## Write a Component

```python
from openrois.components.core import CommandFailed, Component, component, invoke, subscribe
from openrois.interfaces.components import NAVIGATION_PROFILE
from openrois.interfaces.service import CompletedStatus


@component(NAVIGATION_PROFILE)
class Navigation(Component):
    def __init__(self, robot_url: str) -> None:
        self._robot_url = robot_url

    async def connect(self) -> None:
        self._robot = await MyRobotClient.open(self._robot_url)

    async def disconnect(self) -> None:
        await self._robot.close()

    @invoke("start")
    async def start(self) -> dict[str, object]:
        target = self.parameters["target_positions"][0]
        if not await self._robot.knows(target):
            raise CommandFailed(CompletedStatus.ERROR, f"unknown place {target}")
        await self._robot.go_to(target)  # the command runs until the robot arrives
        self.emit("reached_target", target=target, is_final_target=True)
        return {}

    @invoke("stop")
    async def stop(self) -> None:
        await self._robot.halt()

    @subscribe("reached_target")
    async def reached_target(self) -> None:
        pass  # start emits the event when the robot arrives.
```

**The profile.** `@component` takes the profile of the component type. For a basic RoIS
component, pass its constant from `openrois.interfaces.components`, for example
`NAVIGATION_PROFILE`. For a type of your own, pass a full `HRIComponentProfile`. A
handler for a message the profile does not define fails when the class is defined.

**What the engine serves.** A component may implement a part of its type. The engine
serves the commands, queries and events the class has handlers for, and
`component_status`, which the engine answers itself. A type that includes RoISCommon,
as every basic type but SystemInformation does, always serves `start`, `stop`, `suspend`
and `resume`, with or without handlers, and a type of your own without it serves `stop`
when the class handles `start`. The class above serves `start`, `stop`, `suspend`,
`resume`, `component_status` and `reached_target`, and a client never sees a button for
a message the component does not answer.

**RoIS_Common.** The engine answers the four RoIS_Common commands by default. `stop`
cancels the running `start`, which ends with ABORT. `suspend` holds the component's
later commands in the engine, except `set_parameter`, and drops its events, and `resume`
releases both. On a component not started, the three complete OK and run no handler. A
handler for any of them adds to the default and never replaces it: write one when the
function needs more, such as pausing a detector's watcher.

**Commands.** A command handler runs for as long as the command lasts, and the engine
reports the end with `rois.command.completed`. Returning ends the command with OK, and the
returned values become the results that `get_command_result` reads. Raising
`CommandFailed` ends it with the status it names, and any other exception with ERROR. A
`stop`, or a new `start`, runs the `stop` handler and then cancels the running `start`,
which ends with ABORT. Release the backend in a `finally` block if the handler needs to.

**Arguments and results.** A command handler takes the arguments of its command by name,
converted from their profile types. Command and query handlers return the values of their
results by name, and the SDK writes each value in the form its profile type takes on the
wire, so names and types come from the profile.

**Parameters.** `self.parameters` holds the current values, converted from their profile
types: a `string[]` parameter reads as a list. The engine stores them, fills them from the
profile defaults and answers `get_parameter`. To apply new values to the backend, or to
refuse them, mark a method with `@on_set_parameter`:

```python
    @on_set_parameter
    async def apply(self, values: Mapping[str, Any]) -> None:
        if "routing_policy" in values:
            await self._robot.set_policy(values["routing_policy"])
```

Raising refuses the values, and the engine keeps the old ones.

**Events.** `@subscribe` marks an event the component emits. Its method runs on each new
subscription, for example to start a detector, and may do nothing. `self.emit` sends an
event with its results by name, and is safe to call from any thread, for example a ROS 2
callback.

**Arguments of queries and events.** Some queries and events take arguments, such as the
`stream_id` of `get_stream_status` and `notify_stream_status`. A client gives them in the
condition, and the handler and the `@subscribe` method take them by name. An event about
one stream names its values when it is emitted, so it reaches the subscriptions for that
stream only:

```python
    self.emit("notify_stream_status", concerning={"stream_id": stream_id}, status=status)
```

**Status.** A component reports trouble with `self.raise_status(ComponentStatus.WARNING,
"The battery is low.")` or with ERROR, and withdraws it with `self.clear_status()`. Clients
see it in `component_status` and receive `rois.system.notify_error`. While ERROR is
raised, the engine refuses the component's commands and queries. Both methods are safe to
call from any thread.

**Shared resources.** A connection that several components of one adapter share, such as
one robot SDK client, is a `Resource`. The adapter builds it and hands it to each
component, which records it with `self.uses(resource)`. The engine opens it before the
first of them connects and closes it after the last one disconnects, and a status the
resource raises reaches every component that uses it:

```python
class RobotConnection(Resource):
    async def open(self) -> None:
        self.client = RobotClient(self._host)

    async def close(self) -> None:
        await self.client.disconnect()


@component(SPEECH_SYNTHESIS_PROFILE)
class Speech(Component):
    def __init__(self, robot: RobotConnection) -> None:
        self._robot = self.uses(robot)
```

## API

| Name | Purpose |
|------|---------|
| `Component` | Base class of a component: `parameters`, `emit`, `ref`, `connect()`, `disconnect()`, `uses`, `raise_status`, `clear_status`, `engine_state` |
| `Resource` | Base class of what several components share: `open()`, `close()`, `raise_status`, `clear_status` |
| `@component(profile)` | Declare the component type, checked against the handlers |
| `@invoke(command_type)` | Mark the handler of a command |
| `@query(query_type)` | Mark the handler of a query |
| `@subscribe(event_type)` | Mark an event the component emits, with a method run on each subscription |
| `@on_set_parameter` | Mark the hook that applies new parameter values |
| `CommandFailed(status)` | End a command with ERROR, ABORT, OUT_OF_RESOURCES or TIMEOUT |
| `EngineBinding` | What a component needs from the engine that hosts it |

The methods whose names start with `rois_` are called by the engine, not by component
authors.

## Test

```bash
pip install -e ./interfaces/python -e "./components/core[dev]"
cd components/core && pytest && mypy && ruff check src/ tests/
```

## Status

Alpha, pre-1.0, unstable API. The engine that hosts components written with this SDK,
`openrois-engine`, answers the RoIS method catalog with the behavior of CP1 to CP3. A
hook for the moment a component loses its last bind is planned. The Reachy Mini
adapter, [openrois-adapter-reachy-mini](https://github.com/openrois/openrois-adapter-reachy-mini),
is a complete example of components written with this SDK.

## License

Apache-2.0.
