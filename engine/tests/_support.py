"""Helpers for the engine tests: a JSON-RPC client, adapters and fake child engines.

Every test runs a real WsServer on an ephemeral loopback port. Clients and
adapters connect to it over real WebSockets, so the tests cover the transport
as deployed, not a mock of it.
"""


from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openrois.interfaces.contract import InvokeResponse
from openrois.interfaces.hri import ReturnCode
from openrois_components_core import (
    component,
    invoke,
    meta_from_decorators,
    query,
    results,
    subscribe,
)
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from openrois.engine import Engine, WsClient, WsServer

#: How long a gateway in the tests waits for a child engine's reply.
CHILD_TIMEOUT = 0.5


async def wait_until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    """Poll a condition until it holds, failing the test after ``timeout`` seconds."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        if loop.time() > deadline:
            raise AssertionError("Condition not met in time.")
        await asyncio.sleep(0.01)


# ---------------------------------------------------------------------------
# A component for the adapters in the tests
# ---------------------------------------------------------------------------


@component("Navigation", function="actuation")
class Navigation:
    """An actuation component whose ``hold`` command runs until released."""

    def __init__(self) -> None:
        self.release_hold = asyncio.Event()

    @query("component_status")
    async def status(self) -> list[Any]:
        return results.status("READY")

    @invoke("start")
    async def start(self, parameters: list[Any]) -> InvokeResponse:
        return InvokeResponse(return_code=ReturnCode.OK)

    @invoke("hold")
    async def hold(self, parameters: list[Any]) -> InvokeResponse:
        await self.release_hold.wait()
        return InvokeResponse(return_code=ReturnCode.OK)

    @subscribe("reached_target")
    async def on_subscribe(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Gateway, clients and adapters
# ---------------------------------------------------------------------------


@dataclass
class Gateway:
    """A running gateway: the engine and the server in front of it."""

    engine: Engine
    server: WsServer

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.server.port}"

    def child_ids(self) -> list[str]:
        return [str(entry["engine_id"]) for entry in self.engine.get_sub_engines()]



class RpcClient:
    """A JSON-RPC client that matches replies by id and queues notifications."""

    def __init__(self, connection: ClientConnection) -> None:
        self.connection = connection
        self.notifications: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0
        self._reader = asyncio.create_task(self._read())

    @classmethod
    async def connect(cls, url: str) -> RpcClient:
        return cls(await connect(url))

    async def _read(self) -> None:
        try:
            async for raw in self.connection:
                message = json.loads(raw)
                future = self._pending.pop(message.get("id"), None) if "id" in message else None
                if future is not None:
                    future.set_result(message)
                else:
                    await self.notifications.put(message)
        except ConnectionClosed:
            pass

    def send(
        self, method: str, params: dict[str, Any] | None = None
    ) -> asyncio.Future[dict[str, Any]]:
        """Send a request and return a future for the whole reply."""
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[self._next_id] = future
        message = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}}
        asyncio.ensure_future(self.connection.send(json.dumps(message)))
        return future

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a request and return its result."""
        reply = await asyncio.wait_for(self.send(method, params), timeout=2.0)
        assert "result" in reply, reply
        result: dict[str, Any] = reply["result"]
        return result

    async def notification(self, method: str, timeout: float = 2.0) -> dict[str, Any]:
        """Return the params of the next notification with this method."""
        while True:
            message = await asyncio.wait_for(self.notifications.get(), timeout=timeout)
            if message.get("method") == method:
                params: dict[str, Any] = message.get("params", {})
                return params

    async def close(self) -> None:
        await self.connection.close()
        await self._reader



@dataclass
class Adapter:
    """A running adapter with one Navigation component."""

    engine: Engine
    navigation: Navigation
    task: asyncio.Task[None]

    async def stop(self) -> None:
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


async def start_adapter(gateway: Gateway, engine_id: str = "robot") -> Adapter:
    """Start an adapter and wait until the gateway has registered it."""
    engine = Engine(engine_id=engine_id, platform="test")
    navigation = Navigation()
    meta = meta_from_decorators(Navigation)
    engine.register_component(meta.ref, navigation, meta)
    task = asyncio.create_task(WsClient(engine, gateway.url).run_async())
    await wait_until(lambda: engine_id in gateway.child_ids())
    return Adapter(engine, navigation, task)



class FakeChild:
    """A child engine written by hand, for discovery replies an adapter never sends."""

    def __init__(self, connection: ClientConnection) -> None:
        self.connection = connection

    @classmethod
    async def connect(cls, gateway: Gateway) -> FakeChild:
        return cls(await connect(f"{gateway.url}/adapter"))

    async def answer_search(self, engine_id: str) -> None:
        """Answer the gateway's rois.command.search with one component."""
        request = json.loads(await self.connection.recv())
        assert request["method"] == "rois.command.search"
        reply = {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "return_code": "OK",
                "component_ref_list": ["Camera"],
                "components": [{"ref": "Camera", "function": "sensing", "queries": []}],
                "profile": {"identifier": {"code": engine_id}, "platform": "fake"},
            },
        }
        await self.connection.send(json.dumps(reply))

    async def closed(self) -> tuple[int | None, str | None]:
        """Wait until the gateway closes the connection, and return code and reason."""
        await asyncio.wait_for(self.connection.wait_closed(), timeout=2.0)
        return self.connection.close_code, self.connection.close_reason
