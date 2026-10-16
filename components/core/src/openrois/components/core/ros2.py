"""RclpyExecutor: the one rclpy executor that spins the ROS 2 nodes of an adapter.

The components of an adapter that talk ROS 2 share one RclpyExecutor. Each records it
with ``Component.uses``, creates its node in ``connect()``, hands it over with
``add_node``, and takes it back with ``remove_node`` in ``disconnect()``::

    from openrois.components.core.ros2 import RclpyExecutor

    @component(NAVIGATION_PROFILE)
    class Navigation(Component):
        def __init__(self, ros: RclpyExecutor) -> None:
            self._ros = self.uses(ros)

        async def connect(self) -> None:
            from rclpy.node import Node

            self._node = Node("navigation")
            self._ros.add_node(self._node)

        async def disconnect(self) -> None:
            self._ros.remove_node(self._node)
            self._node.destroy_node()

    ros = RclpyExecutor()
    engine.add_component("navigation", Navigation(ros))

The engine opens the executor before the first of those components connects and closes
it after the last one disconnects, so a component can still send ROS 2 requests while it
disconnects. The node callbacks run on the executor's threads, never on the event loop.

rclpy is imported when the executor opens, so this module imports without ROS 2. Where
rclpy is missing, ``open()`` raises and every component that uses the executor reports
ERROR.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from openrois.components.core.resource import Resource

logger = logging.getLogger(__name__)

# How long close() waits for the executor and its spinning thread to stop, in seconds.
_SHUTDOWN_TIMEOUT = 5.0


class RclpyExecutor(Resource):
    """Owns rclpy init and shutdown, and spins every node handed to it in one thread."""

    def __init__(self) -> None:
        self._executor: Any = None
        self._thread: threading.Thread | None = None
        # Whether open() initialized rclpy, and close() must shut it down. A process
        # that initialized rclpy itself keeps it.
        self._initialized = False

    async def open(self) -> None:
        """Initialize rclpy, unless it already is, and start spinning.

        Raises:
            ImportError: rclpy is not installed.
        """
        import rclpy
        from rclpy.executors import MultiThreadedExecutor

        if not rclpy.ok():
            rclpy.init()
            self._initialized = True
        self._executor = MultiThreadedExecutor()
        self._thread = threading.Thread(target=self._executor.spin, daemon=True, name="rclpy-spin")
        self._thread.start()
        logger.info("Spinning ROS 2 nodes in a background thread")

    async def close(self) -> None:
        """Stop spinning, and shut rclpy down if open() initialized it."""
        executor, thread = self._executor, self._thread
        self._executor = None
        self._thread = None
        if executor is None:
            return
        # The shutdown waits for running callbacks, so it runs off the event loop.
        await asyncio.to_thread(executor.shutdown, _SHUTDOWN_TIMEOUT)
        if thread is not None:
            await asyncio.to_thread(thread.join, _SHUTDOWN_TIMEOUT)
        if self._initialized:
            import rclpy

            rclpy.shutdown()
            self._initialized = False
        logger.info("Stopped spinning ROS 2 nodes")

    def add_node(self, node: Any) -> None:
        """Spin a node. Call it from ``connect()``, once the engine has opened the executor.

        Raises:
            RuntimeError: The executor is not open.
        """
        self._open_executor().add_node(node)

    def remove_node(self, node: Any) -> None:
        """Stop spinning a node, before the component destroys it.

        Raises:
            RuntimeError: The executor is not open.
        """
        self._open_executor().remove_node(node)

    def _open_executor(self) -> Any:
        if self._executor is None:
            raise RuntimeError(
                "The RclpyExecutor is not open. Record it with Component.uses so the "
                "engine opens it before connect()."
            )
        return self._executor
