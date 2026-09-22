"""Shared fixtures: an engine with local mock components and a recording sink."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from openrois.interfaces.bus import EventEnvelope, InvokeResponse
from openrois.interfaces.hri import Result, ReturnCode
from openrois_components_core import (
    component,
    invoke,
    meta_from_decorators,
    query,
    results,
    subscribe,
)

from openrois_core import Engine, EventEmitter


@component("SystemInformation")
class FakeSystemInformation:
    """A sensing component with queries only."""

    @query("robot_position")
    async def robot_position(self) -> list[Result]:
        return results.position(x=1.0, y=2.0, theta=0.5)

    @query("component_status")
    async def status(self) -> list[Result]:
        return results.status("READY")


@component("Navigation", function="actuation")
class FakeNavigation:
    """An actuation component that records what it receives and emits on demand."""

    def __init__(self) -> None:
        self.received: list[list[dict[str, Any]]] = []
        self.parameters: list[dict[str, Any]] = []
        self.subscribed = 0

    @query("component_status")
    async def status(self) -> list[Result]:
        return results.status("READY")

    @invoke("set_parameter")
    async def set_parameter(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        self.parameters = parameters
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("execute")
    async def execute(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        self.received.append(parameters)
        return InvokeResponse(return_code=ReturnCode.OK, command_id="cmd-nav")

    @invoke("stop")
    async def stop(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        raise RuntimeError("stop is broken on purpose")

    @subscribe("reached_target")
    async def on_reached(self) -> None:
        self.subscribed += 1

    async def arrive(self, target: str) -> None:
        await self.parent.emit_async(  # type: ignore[attr-defined]
            "Navigation", "reached_target",
            results.reached_target(target=target, is_final_target=True),
        )


def build_engine(**kwargs: Any) -> tuple[Engine, FakeNavigation]:
    """An engine with the two fake components registered and an emitter attached."""
    engine = Engine(engine_id=kwargs.pop("engine_id", "robot_1"), platform="fake", **kwargs)
    engine.component_registry.set_emitter(EventEmitter(asyncio.get_running_loop()))
    nav = FakeNavigation()
    for ref, handler in (("SystemInformation", FakeSystemInformation()), ("Navigation", nav)):
        meta = meta_from_decorators(type(handler))
        engine.register_component(ref, handler, meta)
    return engine, nav


class RecordingSink:
    """An EventSink that keeps every envelope it receives."""

    def __init__(self) -> None:
        self.envelopes: list[EventEnvelope] = []
        self.arrived = asyncio.Event()

    async def __call__(self, envelope: EventEnvelope) -> None:
        self.envelopes.append(envelope)
        self.arrived.set()


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink()


@pytest.fixture
def make_engine() -> Callable[..., tuple[Engine, FakeNavigation]]:
    return build_engine
