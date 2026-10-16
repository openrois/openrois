"""Adapter template: the starting point of an adapter for your robot, avatar or service.

Copy this directory and fill in every ``IMPLEMENT YOUR CODE HERE`` block with calls to
the API of your platform: an HTTP client, a gRPC stub, a ROS 2 node, a serial port. The
connection to the robot is a Resource that the three components share, and the settings
come from ``adapter.yaml`` through the engine's adapter loader. The three components show
the kinds of component an adapter hosts:

- ``MyNavigation``: a basic RoIS component type, declared with its profile constant. It
  implements a part of the type, ``start`` and ``stop``, and the engine serves that part.
- ``MySystemInformation``: another basic type, with queries only.
- ``Battery``: a type of your own, with a profile of its own, for what the basic types
  do not cover.

Usage:
    python my_adapter.py [--config FILE] [--robot-address URL] [--gateway-url URL]
                         [--engine-id ID] [--log-level LEVEL]

Each setting comes from the defaults of MyAdapterConfig, then ``adapter.yaml`` (named by
``--config`` or ``OPENROIS_ADAPTER_CONFIG``), then the ``OPENROIS_ADAPTER_*`` environment
variables, then the flags.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime

from openrois.components.core import (
    CommandFailed,
    Component,
    Resource,
    component,
    invoke,
    query,
    subscribe,
)
from openrois.engine import Engine, WsClient
from openrois.engine.config import AdapterConfig, ConfigError, load_adapter_config
from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components import (
    NAVIGATION_PROFILE,
    ROIS_COMMON_PROFILE,
    ROIS_COMMON_URN,
    SYSTEM_INFORMATION_PROFILE,
)
from openrois.interfaces.profiles import (
    ComponentFunction,
    EventMessageProfile,
    HRIComponentProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from openrois.interfaces.service import CompletedStatus
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("my_adapter")


# ─── The settings ────────────────────────────────────────────


class BatterySettings(BaseModel):
    """The ``battery`` section of adapter.yaml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check_interval: float = Field(default=30.0, gt=0, description="Seconds between checks.")


class MyAdapterConfig(AdapterConfig):
    """The settings of the adapter: the four common ones, and one section per component
    that has settings of its own. Only the four common ones come from the environment and
    the flags."""

    engine_id: str = "my_robot"
    robot_address: str | None = "http://127.0.0.1:8080"
    battery: BatterySettings = BatterySettings()


# ─── The connection the components share ─────────────────────


class RobotConnection(Resource):
    """The connection to the robot. The engine opens it once, before the first component
    that uses it connects, and closes it after the last one disconnects."""

    def __init__(self, address: str) -> None:
        self.address = address

    async def open(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        # Create the client of your platform's API. Raise only for what waiting cannot
        # fix, such as a missing SDK: every component that uses the connection then
        # reports ERROR. A robot that is not reachable yet is a status:
        # self.raise_status(ComponentStatus.WARNING, "The robot is not answering.")
        logger.info("Would connect to the robot at %s", self.address)

    async def close(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        # Close the client.
        pass


# ─── A basic component type ──────────────────────────────────


@component(NAVIGATION_PROFILE)
class MyNavigation(Component):
    """Navigation: drives to the first of ``target_positions``.

    The engine stores the parameters, reserves the component for the client that binds
    it, and reports BUSY while ``start`` runs. ``stop``, or a new ``start``, runs
    ``stop`` and then cancels the running ``start``, which ends with ABORT.
    """

    def __init__(self, robot: RobotConnection) -> None:
        self._robot = self.uses(robot)

    @invoke("start")
    async def start(self) -> None:
        targets = self.parameters.get("target_positions", [])
        if not targets:
            # The command ends with the status CommandFailed names, here ERROR.
            raise CommandFailed(CompletedStatus.ERROR, "Set target_positions first.")
        target = targets[0]
        await self._drive_to(target)
        self.emit("reached_target", target=target, is_final_target=True)

    @invoke("stop")
    async def stop(self) -> None:
        await self._halt()

    @subscribe("reached_target")
    async def reached_target(self) -> None:
        pass  # start emits the event when the robot arrives.

    async def _drive_to(self, target: str) -> None:
        # IMPLEMENT YOUR CODE HERE
        # Drive to the target and return when the robot arrives. Raise
        # CommandFailed(CompletedStatus.ERROR, "why") when the robot cannot get there.
        raise NotImplementedError(f"drive to {target}")

    async def _halt(self) -> None:
        # IMPLEMENT YOUR CODE HERE
        # Stop the robot where it is.
        raise NotImplementedError("halt")


@component(SYSTEM_INFORMATION_PROFILE)
class MySystemInformation(Component):
    """SystemInformation: where the robot is, and since when the engine runs."""

    def __init__(self, robot: RobotConnection) -> None:
        self._robot = self.uses(robot)
        self._started = datetime.now(UTC)

    @query("robot_position")
    async def robot_position(self) -> dict[str, object]:
        x, y, theta = await self._read_pose()
        return {
            "position_data": [f"{x},{y},{theta}"],
            "robot_ref": [self.ref.split("/", 1)[0]],
            "timestamp": datetime.now(UTC),
        }

    @query("engine_status")
    async def engine_status(self) -> dict[str, object]:
        return {"operable_time": self._started, "status": ComponentStatus.READY}

    async def _read_pose(self) -> tuple[float, float, float]:
        # IMPLEMENT YOUR CODE HERE
        # Read the pose of the robot: x and y in meters, theta in radians.
        raise NotImplementedError("read the pose")


# ─── A component type of your own ────────────────────────────


def _parameter(name: str, code: str, description: str, default: str = "") -> ParameterProfile:
    return ParameterProfile(
        name=name,
        data_type_ref=RoISIdentifierType(code=code),
        description=description,
        default_value=default,
    )


#: The profile of a type no basic RoIS component covers. Name the authority after your
#: organization, include RoIS_Common for component_status, which the engine answers, and
#: declare every message and parameter the type has. A client discovers them from the
#: profile, as it does for the basic types.
BATTERY_PROFILE = HRIComponentProfile(
    identifier=RoISIdentifierType(authority="MyOrganization", code="Battery"),
    name="battery",
    function=ComponentFunction.SENSING,
    sub_component_profiles=[ROIS_COMMON_URN],
    query_profiles=[
        *ROIS_COMMON_PROFILE.query_profiles,
        QueryMessageProfile(
            name="battery_level",
            results=[_parameter("percentage", "double", "remaining charge, 0 to 100")],
        ),
    ],
    event_profiles=[
        EventMessageProfile(
            name="battery_low",
            results=[_parameter("percentage", "double", "remaining charge, 0 to 100")],
        ),
    ],
    parameter_profiles=[
        _parameter("low_threshold", "double", "charge below which battery_low fires", "20"),
    ],
)


@component(BATTERY_PROFILE)
class Battery(Component):
    """Battery: the charge of the robot, and an event when it runs low."""

    def __init__(self, robot: RobotConnection, settings: BatterySettings) -> None:
        self._robot = self.uses(robot)
        self._check_interval = settings.check_interval
        self._monitor: asyncio.Task[None] | None = None

    async def disconnect(self) -> None:
        if self._monitor is not None:
            self._monitor.cancel()
            await asyncio.gather(self._monitor, return_exceptions=True)
            self._monitor = None

    @query("battery_level")
    async def battery_level(self) -> dict[str, object]:
        return {"percentage": await self._read_level()}

    @subscribe("battery_low")
    async def battery_low(self) -> None:
        # The first subscription starts the monitor. The engine sends each event to every
        # subscription.
        if self._monitor is None:
            self._monitor = asyncio.create_task(self._watch())

    async def _watch(self) -> None:
        while True:
            try:
                level = await self._read_level()
                if level < self.parameters["low_threshold"]:
                    self.emit("battery_low", percentage=level)
            except Exception:
                logger.exception("Could not read the battery level")
            await asyncio.sleep(self._check_interval)

    async def _read_level(self) -> float:
        # IMPLEMENT YOUR CODE HERE
        # Read the remaining charge of the robot, 0 to 100.
        raise NotImplementedError("read the battery level")


# ─── The adapter ─────────────────────────────────────────────


def main() -> None:
    """Host the components in an engine and serve them to the gateway until Ctrl+C."""
    try:
        config = load_adapter_config(
            MyAdapterConfig, description="An OpenRoIS adapter for my robot."
        )
    except ConfigError as exc:
        print(f"my_adapter: {exc}", file=sys.stderr)
        sys.exit(2)
    if config.robot_address is None:
        print("my_adapter: robot_address is not set.", file=sys.stderr)
        sys.exit(2)
    logging.basicConfig(level=config.log_level.upper())

    robot = RobotConnection(config.robot_address)
    engine = Engine(config.engine_id)
    engine.add_component("navigation", MyNavigation(robot))
    engine.add_component("system_information", MySystemInformation(robot))
    engine.add_component("battery", Battery(robot, config.battery))
    WsClient(engine, config.gateway_url).run()


if __name__ == "__main__":
    main()
