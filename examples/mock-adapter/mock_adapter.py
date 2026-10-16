"""A mock adapter: the components of the TypeScript mock engine, on the Python engine.

It hosts three simulated components under the engine id ``mock``, each declared with
the profile constant of its type, and serves them to a gateway:

- ``mock/person_detection`` reports zero to three persons every five seconds.
- ``mock/navigation`` drives to the first of its ``target_positions`` in three seconds
  and reports ``reached_target``.
- ``mock/system_information`` answers ``robot_position`` and ``engine_status``.

Usage:
    python mock_adapter.py [--config FILE] [--gateway-url URL] [--engine-id ID]
                           [--log-level LEVEL]

The settings come from the engine's adapter loader: the defaults of MockConfig, then
``adapter.yaml`` (named by ``--config`` or ``OPENROIS_ADAPTER_CONFIG``), then the
``OPENROIS_ADAPTER_*`` environment variables, then the flags. ``time_scale`` in the file
multiplies every delay. ``adapter.fast.yaml`` sets it to ``0.1``, for tests that should not
wait.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from openrois.components.common import MockSystemInformation
from openrois.components.core import (
    CommandFailed,
    Component,
    component,
    invoke,
    on_set_parameter,
    subscribe,
)
from openrois.engine import Engine, WsClient
from openrois.engine.config import AdapterConfig, ConfigError, load_adapter_config
from openrois.interfaces.components import NAVIGATION_PROFILE, PERSON_DETECTION_PROFILE
from openrois.interfaces.service import CompletedStatus
from pydantic import Field

logger = logging.getLogger("mock_adapter")


class MockConfig(AdapterConfig):
    """The settings of the mock adapter. It reaches no robot, so robot_address is unused."""

    engine_id: str = "mock"
    time_scale: float = Field(
        default=1.0, gt=0, description="Factor on every delay, below 1 for faster tests."
    )


@dataclass(frozen=True)
class Timing:
    """How long the simulated work takes, in seconds. The TypeScript mock engine's values.

    Attributes:
        command: A command or a parameter change, other than a navigation.
        navigation: A navigation, from start to reached_target.
        detection: The interval between two person_detected events.
    """

    command: float = 0.2
    navigation: float = 3.0
    detection: float = 5.0

    def scaled(self, factor: float) -> Timing:
        """The same timing with every delay multiplied by ``factor``."""
        return Timing(self.command * factor, self.navigation * factor, self.detection * factor)


#: Navigation with ``["home"]`` as the default of target_positions. Navigation.xml gives
#: none, and the default lets a client start a navigation before setting any parameter.
NAVIGATION_WITH_HOME = NAVIGATION_PROFILE.model_copy(
    update={
        "parameter_profiles": [
            p.model_copy(update={"default_value": '["home"]'})
            if p.name == "target_positions"
            else p
            for p in NAVIGATION_PROFILE.parameter_profiles
        ]
    }
)


@component(PERSON_DETECTION_PROFILE)
class MockPersonDetection(Component):
    """Counts zero to three persons in turn, and reports the count while connected."""

    def __init__(self, timing: Timing) -> None:
        self._timing = timing
        self._detector: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        self._detector = asyncio.create_task(self._detect())

    async def disconnect(self) -> None:
        if self._detector is not None:
            self._detector.cancel()
            await asyncio.gather(self._detector, return_exceptions=True)

    async def _detect(self) -> None:
        count = 0
        while True:
            await asyncio.sleep(self._timing.detection)
            count = (count + 1) % 4
            # The engine sends the event to every subscription, and drops it when there
            # is none.
            self.emit("person_detected", number=count, timestamp=datetime.now(UTC))

    @invoke("start")
    async def start(self) -> None:
        await asyncio.sleep(self._timing.command)

    @invoke("stop")
    async def stop(self) -> None:
        await asyncio.sleep(self._timing.command)

    @invoke("suspend")
    async def suspend(self) -> None:
        await asyncio.sleep(self._timing.command)

    @invoke("resume")
    async def resume(self) -> None:
        await asyncio.sleep(self._timing.command)

    @subscribe("person_detected")
    async def person_detected(self) -> None:
        pass  # The detector emits the event on its own.


@component(NAVIGATION_WITH_HOME)
class MockNavigation(Component):
    """Drives to the first target position, which takes a few seconds and moves nothing."""

    def __init__(self, timing: Timing) -> None:
        self._timing = timing

    @invoke("start")
    async def start(self) -> None:
        targets = self.parameters.get("target_positions", [])
        if not targets:
            raise CommandFailed(CompletedStatus.ERROR, "target_positions is empty")
        target = targets[0]
        logger.info("Driving to %s", target)
        # A stop, or a new start, cancels the drive here, and it ends with ABORT.
        await asyncio.sleep(self._timing.navigation)
        self.emit("reached_target", target=target, is_final_target=True)
        logger.info("Reached %s", target)

    @invoke("stop")
    async def stop(self) -> None:
        pass  # Nothing moves, so there is nothing to halt.

    @invoke("suspend")
    async def suspend(self) -> None:
        await asyncio.sleep(self._timing.command)

    @invoke("resume")
    async def resume(self) -> None:
        await asyncio.sleep(self._timing.command)

    @subscribe("reached_target")
    async def reached_target(self) -> None:
        pass  # start emits the event when the drive ends.

    @on_set_parameter
    async def apply(self, values: Mapping[str, Any]) -> None:
        logger.info("New parameters: %s", dict(values))
        await asyncio.sleep(self._timing.command)


def build_engine(engine_id: str = "mock", timing: Timing | None = None) -> Engine:
    """The engine of the mock adapter, with its three components."""
    timing = timing or Timing()
    engine = Engine(engine_id)
    engine.add_component("person_detection", MockPersonDetection(timing))
    engine.add_component("navigation", MockNavigation(timing))
    engine.add_component("system_information", MockSystemInformation())
    return engine


def main() -> None:
    """Load the settings and serve the gateway until Ctrl+C."""
    try:
        config = load_adapter_config(MockConfig, description="The OpenRoIS mock adapter.")
    except ConfigError as exc:
        print(f"mock_adapter: {exc}", file=sys.stderr)
        sys.exit(2)

    logging.basicConfig(
        level=config.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    engine = build_engine(config.engine_id, Timing().scaled(config.time_scale))
    WsClient(engine, config.gateway_url).run()


if __name__ == "__main__":
    main()
