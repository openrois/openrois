"""RclpyExecutor against a stand-in for rclpy, hosted by a real engine.

A resource that cannot open fails its components, which the engine's own tests cover, so
these tests check only that a missing rclpy fails open().
"""

from __future__ import annotations

import sys
import threading
import types
from dataclasses import dataclass, field
from typing import Any

import pytest
from openrois.engine import Engine
from openrois.interfaces.components import SYSTEM_INFORMATION_PROFILE

from openrois.components.core import Component, component
from openrois.components.core.ros2 import RclpyExecutor


@dataclass
class FakeRclpy:
    """rclpy with init, shutdown and a MultiThreadedExecutor whose spin blocks.

    ``log`` records every call in order, so a test can check what ran before what.
    """

    initialized: bool = False
    log: list[str] = field(default_factory=list)
    executors: list[Any] = field(default_factory=list)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = self

        class MultiThreadedExecutor:
            def __init__(self) -> None:
                self.nodes: list[Any] = []
                self.spinning_on: str | None = None
                self._stopped = threading.Event()
                fake.executors.append(self)

            def add_node(self, node: Any) -> None:
                fake.log.append(f"add {node}")
                self.nodes.append(node)

            def remove_node(self, node: Any) -> None:
                fake.log.append(f"remove {node}")
                self.nodes.remove(node)

            def spin(self) -> None:
                self.spinning_on = threading.current_thread().name
                fake.log.append("spin")
                self._stopped.wait(timeout=5.0)
                fake.log.append("spin ended")

            def shutdown(self, timeout_sec: float | None = None) -> bool:
                fake.log.append("executor shutdown")
                self._stopped.set()
                return True

        def init() -> None:
            assert not fake.initialized, "rclpy.init called twice"
            fake.initialized = True
            fake.log.append("init")

        def ok() -> bool:
            return fake.initialized

        def shutdown() -> None:
            fake.initialized = False
            fake.log.append("shutdown")

        rclpy = types.ModuleType("rclpy")
        rclpy.init = init  # type: ignore[attr-defined]
        rclpy.ok = ok  # type: ignore[attr-defined]
        rclpy.shutdown = shutdown  # type: ignore[attr-defined]
        executors = types.ModuleType("rclpy.executors")
        executors.MultiThreadedExecutor = MultiThreadedExecutor  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "rclpy", rclpy)
        monkeypatch.setitem(sys.modules, "rclpy.executors", executors)


@pytest.fixture
def rclpy(monkeypatch: pytest.MonkeyPatch) -> FakeRclpy:
    fake = FakeRclpy()
    fake.install(monkeypatch)
    return fake


@component(SYSTEM_INFORMATION_PROFILE)
class NodeComponent(Component):
    """A component that hands one node to the executor while connected."""

    def __init__(self, ros: RclpyExecutor, node: str, log: list[str]) -> None:
        self._ros = self.uses(ros)
        self._node = node
        self._log = log

    async def connect(self) -> None:
        self._log.append(f"connect {self._node}")
        self._ros.add_node(self._node)

    async def disconnect(self) -> None:
        self._ros.remove_node(self._node)
        self._log.append(f"disconnect {self._node}")


class TestOpenAndClose:
    async def test_open_initializes_rclpy_and_spins_in_one_thread(self, rclpy: FakeRclpy) -> None:
        ros = RclpyExecutor()
        await ros.open()
        try:
            [executor] = rclpy.executors
            await _until(lambda: executor.spinning_on is not None)
            assert executor.spinning_on == "rclpy-spin"
            assert rclpy.initialized
        finally:
            await ros.close()
        assert rclpy.log == ["init", "spin", "executor shutdown", "spin ended", "shutdown"]
        assert not rclpy.initialized

    async def test_rclpy_initialized_elsewhere_stays_initialized(self, rclpy: FakeRclpy) -> None:
        rclpy.initialized = True
        ros = RclpyExecutor()
        await ros.open()
        await ros.close()
        assert "init" not in rclpy.log
        assert "shutdown" not in rclpy.log
        assert rclpy.initialized

    async def test_a_missing_rclpy_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # None in sys.modules makes the import fail, as it does where ROS 2 is absent.
        monkeypatch.setitem(sys.modules, "rclpy", None)
        monkeypatch.setitem(sys.modules, "rclpy.executors", None)
        with pytest.raises(ImportError):
            await RclpyExecutor().open()

    async def test_close_without_open_does_nothing(self, rclpy: FakeRclpy) -> None:
        await RclpyExecutor().close()
        assert rclpy.log == []


class TestNodes:
    async def test_added_nodes_reach_the_executor(self, rclpy: FakeRclpy) -> None:
        ros = RclpyExecutor()
        await ros.open()
        try:
            ros.add_node("a")
            ros.add_node("b")
            ros.remove_node("a")
            assert rclpy.executors[0].nodes == ["b"]
        finally:
            await ros.close()

    def test_a_node_needs_an_open_executor(self, rclpy: FakeRclpy) -> None:
        with pytest.raises(RuntimeError, match="not open"):
            RclpyExecutor().add_node("a")


class TestHosted:
    async def test_one_executor_spins_the_nodes_of_every_component(
        self, rclpy: FakeRclpy
    ) -> None:
        ros = RclpyExecutor()
        engine = Engine("robot")
        engine.add_component("first", NodeComponent(ros, "a", rclpy.log))
        engine.add_component("second", NodeComponent(ros, "b", rclpy.log))
        await engine.start()
        assert rclpy.executors[0].nodes == ["a", "b"]
        await engine.stop()
        [executor] = rclpy.executors
        # The nodes leave while the executor still spins, so a component that halts
        # its robot over ROS 2 on disconnect gets its requests out, and rclpy shuts
        # down last.
        log = [entry for entry in rclpy.log if entry != "spin"]
        assert log == [
            "init",
            "connect a",
            "add a",
            "connect b",
            "add b",
            "remove a",
            "disconnect a",
            "remove b",
            "disconnect b",
            "executor shutdown",
            "spin ended",
            "shutdown",
        ]
        assert executor.nodes == []


async def _until(condition: Any) -> None:
    import asyncio

    async with asyncio.timeout(5.0):
        while not condition():
            await asyncio.sleep(0.005)
