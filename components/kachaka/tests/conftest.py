"""An engine that hosts one Kachaka component, and a client session of it."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from openrois.components.core import Component
from openrois.engine import Engine, Session
from openrois.interfaces.catalog import METHODS_BY_NAME
from pydantic import BaseModel


@dataclass
class Robot:
    """An engine with one component under ``kachaka/<name>``, and a trusted session."""

    engine: Engine
    ref: str
    notifications: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    session: Session | None = None

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        assert self.session is not None
        model = METHODS_BY_NAME[method].params.model_validate(params)
        result = await self.engine.handle(self.session, method, model)
        dumped: dict[str, Any] = result.model_dump(mode="json")
        return dumped

    def sent(self, method: str) -> list[dict[str, Any]]:
        return [params for name, params in self.notifications if name == method]

    async def completed(self, command_id: str) -> str:
        """Wait for the completion of a command and return its status."""
        async with asyncio.timeout(5.0):
            while True:
                for params in self.sent("rois.command.completed"):
                    if params["command_id"] == command_id:
                        status: str = params["status"]
                        return status
                await asyncio.sleep(0.005)

    async def execute(self, command_type: str, command_id: str) -> None:
        unit = {"component_ref": self.ref, "command_type": command_type, "command_id": command_id}
        result = await self.call("rois.command.execute", command_unit_list=[unit])
        assert result["return_code"] == "OK", result


@pytest.fixture
async def host() -> AsyncIterator[Callable[[str, Component], Any]]:
    """Host a component in a started engine. The engines stop after the test."""
    engines: list[Engine] = []

    async def start(name: str, hosted: Component) -> Robot:
        engine = Engine("kachaka")
        ref = engine.add_component(name, hosted)
        await engine.start()
        engines.append(engine)
        robot = Robot(engine, ref)

        def notify(method: str, params: BaseModel) -> None:
            robot.notifications.append((method, params.model_dump(mode="json")))

        robot.session = engine.open_session(notify, trusted=True)
        return robot

    yield start
    for engine in engines:
        await engine.stop()
