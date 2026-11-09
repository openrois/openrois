"""A mock adapter: three simulated components on the Python engine.

It hosts simulated components under the engine id ``mock``, the first three declared
with the profile constant of their type, and serves them to a gateway:

- ``mock/person_detection`` reports zero to three persons every five seconds.
- ``mock/navigation`` drives to the first of its ``target_positions`` in three seconds
  and reports ``reached_target``.
- ``mock/system_information`` answers ``robot_position`` and ``engine_status``.
- ``mock/fault`` is a test fixture. Its commands make the error and the profile change
  that the conformance list checks, so a client triggers them with a plain ``execute``.
  Its ``echo`` messages and ``end_with`` give ``testing/conformance/capture.py`` what the
  profiles of the other components never carry: arguments, results and a timeout on a
  command, arguments on a query and an event, and every way a command can end.

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
    command,
    component,
    event,
    query,
)
from openrois.engine import Engine, WsClient
from openrois.engine.config import AdapterConfig, ConfigError, load_adapter_config
from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components import NAVIGATION_PROFILE, PERSON_DETECTION_PROFILE
from openrois.interfaces.declaration import (
    Command,
    ComponentDeclaration,
    Event,
    Param,
    Query,
)
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
    """How long the simulated work takes, in seconds.

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

    @command("start")
    async def start(self) -> None:
        await asyncio.sleep(self._timing.command)

    @command("stop")
    async def stop(self) -> None:
        await asyncio.sleep(self._timing.command)

    @command("suspend")
    async def suspend(self) -> None:
        await asyncio.sleep(self._timing.command)

    @command("resume")
    async def resume(self) -> None:
        await asyncio.sleep(self._timing.command)

    @event("person_detected")
    async def person_detected(self) -> None:
        pass  # The detector emits the event on its own.


@component(NAVIGATION_WITH_HOME)
class MockNavigation(Component):
    """Drives to the first target position, which takes a few seconds and moves nothing."""

    def __init__(self, timing: Timing) -> None:
        self._timing = timing

    @command("start")
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

    @command("stop")
    async def stop(self) -> None:
        pass  # Nothing moves, so there is nothing to halt.

    @command("suspend")
    async def suspend(self) -> None:
        await asyncio.sleep(self._timing.command)

    @command("resume")
    async def resume(self) -> None:
        await asyncio.sleep(self._timing.command)

    @event("reached_target")
    async def reached_target(self) -> None:
        pass  # start emits the event when the drive ends.

    @command("set_parameter")
    async def apply(self, values: Mapping[str, Any]) -> None:
        logger.info("New parameters: %s", dict(values))
        await asyncio.sleep(self._timing.command)


#: How long mock/fault holds an error, and how long the peer engine stays, in seconds.
FAULT_HOLD = 1.0

#: The timeout of the echo command in milliseconds, far above what it takes to start, so
#: that it only puts a timeout in the profile.
ECHO_TIMEOUT = 5000

#: What every echo message takes and gives back.
ECHO_TEXT = Param("text", "string")

TEST_FAULT_PROFILE = ComponentDeclaration(
    identifier="urn:x-rois:def:component:OpenRoIS::TestFault",
    name="test_fault",
    function="function",
    commands=(
        Command("raise_error"),
        Command("peer_join"),
        Command("echo", arguments=[ECHO_TEXT], results=[ECHO_TEXT], timeout=ECHO_TIMEOUT),
        Command("end_with", arguments=[Param("status", "string")]),
    ),
    queries=(Query("echo", arguments=[ECHO_TEXT], results=[ECHO_TEXT]),),
    events=(Event("echoed", arguments=[ECHO_TEXT], results=[ECHO_TEXT]),),
    sub_profiles=(),
).profile()


@component(TEST_FAULT_PROFILE)
class MockFault(Component):
    """Makes an error, a profile change or a chosen end of a command, on request."""

    def __init__(self, gateway_url: str) -> None:
        self._gateway_url = gateway_url

    @command("raise_error")
    async def raise_error(self) -> None:
        self.raise_status(ComponentStatus.ERROR, "raised on request")
        # An engine refuses every command of a component in ERROR, so no command could
        # clear this one.
        asyncio.get_running_loop().call_later(FAULT_HOLD, self.clear_status)

    @command("peer_join")
    async def peer_join(self) -> None:
        # A second engine joins the gateway and leaves it, which leaves this one alone.
        peer = asyncio.create_task(WsClient(Engine("mock_peer"), self._gateway_url).run_async())
        await asyncio.sleep(FAULT_HOLD)
        peer.cancel()
        await asyncio.gather(peer, return_exceptions=True)

    @command("echo")
    async def echo(self, text: str) -> dict[str, str]:
        self.emit("echoed", concerning={"text": text}, text=text)
        return {"text": text}

    @command("end_with")
    async def end_with(self, status: str) -> None:
        raise CommandFailed(CompletedStatus(status), "ended on request")

    @query("echo")
    async def answer_echo(self, text: str) -> dict[str, str]:
        return {"text": text}

    @event("echoed")
    async def echoed(self, text: str | None = None) -> None:
        pass  # The echo command emits the event.


def build_engine(
    engine_id: str = "mock",
    timing: Timing | None = None,
    gateway_url: str = "ws://127.0.0.1:8765",
) -> Engine:
    """The engine of the mock adapter, with its components."""
    timing = timing or Timing()
    engine = Engine(engine_id)
    engine.add_component("person_detection", MockPersonDetection(timing))
    engine.add_component("navigation", MockNavigation(timing))
    engine.add_component("system_information", MockSystemInformation())
    engine.add_component("fault", MockFault(gateway_url))
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
    engine = build_engine(
        config.engine_id, Timing().scaled(config.time_scale), config.gateway_url
    )
    WsClient(engine, config.gateway_url).run()


if __name__ == "__main__":
    main()
