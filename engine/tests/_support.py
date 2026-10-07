"""Helpers for the engine tests: components, peers, gateways, adapters and fake children.

The components are written with openrois-components-core, as an adapter author writes
them. ``Peer`` drives an engine through the JSON-RPC framing without a socket. The
gateway and adapter helpers run a real WsServer on an ephemeral loopback port, so those
tests cover the transport as deployed.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from openrois.components.core import (
    CommandFailed,
    Component,
    component,
    invoke,
    on_set_parameter,
    query,
    subscribe,
)
from openrois.interfaces.components import NAVIGATION_PROFILE, PERSON_DETECTION_PROFILE
from openrois.interfaces.profiles import (
    CommandMessageProfile,
    ComponentFunction,
    HRIComponentProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from openrois.interfaces.service import CompletedStatus
from pydantic import BaseModel
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from openrois.engine import Engine, WsClient, WsServer
from openrois.engine.jsonrpc import answer

#: How long a gateway in the tests waits for a child engine's reply.
CHILD_TIMEOUT = 0.5


async def wait_until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    """Poll a condition until it holds, failing the test after ``timeout`` seconds."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        if loop.time() > deadline:
            raise AssertionError("Condition not met in time.")
        await asyncio.sleep(0.005)


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


@component(NAVIGATION_PROFILE)
class Navigation(Component):
    """A Navigation whose start runs until the test lets the robot arrive."""

    def __init__(self, *, fail_connect: bool = False) -> None:
        self.fail_connect = fail_connect
        self.connected = False
        self.arrive = asyncio.Event()
        self.applied: list[dict[str, Any]] = []
        self.refuse = False
        self.stops = 0
        self.subscribed = 0

    async def connect(self) -> None:
        if self.fail_connect:
            raise RuntimeError("The robot does not answer.")
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    @invoke("start")
    async def start(self) -> None:
        target = self.parameters.get("target_positions", ["home"])[0]
        await self.arrive.wait()
        self.emit("reached_target", target=target, is_final_target=True)

    @invoke("stop")
    async def stop(self) -> None:
        self.stops += 1

    @invoke("suspend")
    async def suspend(self) -> None:
        raise CommandFailed(CompletedStatus.OUT_OF_RESOURCES, "The brakes are hot.")

    @invoke("resume")
    async def resume(self) -> None:
        raise RuntimeError("The motor driver is gone.")

    @subscribe("reached_target")
    async def reached_target(self) -> None:
        self.subscribed += 1

    @on_set_parameter
    async def apply(self, values: Mapping[str, Any]) -> None:
        if self.refuse:
            raise CommandFailed(CompletedStatus.ERROR, "Unknown place.")
        self.applied.append(dict(values))


@component(PERSON_DETECTION_PROFILE)
class PersonDetection(Component):
    """A sensing component: its commands need no binding.

    With ``ticking``, it emits person_detected every millisecond while it is connected,
    whether anyone subscribed or not.
    """

    def __init__(self, *, ticking: bool = False) -> None:
        self._ticking = ticking
        self._ticker: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        if self._ticking:
            self._ticker = asyncio.create_task(self._tick())

    async def disconnect(self) -> None:
        if self._ticker is not None:
            self._ticker.cancel()
            await asyncio.gather(self._ticker, return_exceptions=True)

    async def _tick(self) -> None:
        count = 0
        while True:
            count += 1
            self.emit("person_detected", number=count)
            await asyncio.sleep(0.001)

    @invoke("start")
    async def start(self) -> None:
        return None

    @subscribe("person_detected")
    async def person_detected(self) -> None:
        return None


def _parameter(name: str, code: str) -> ParameterProfile:
    return ParameterProfile(name=name, data_type_ref=RoISIdentifierType(code=code))


#: A component type of our own, with arguments, results and a timeout.
GRIPPER_PROFILE = HRIComponentProfile(
    identifier=RoISIdentifierType(authority="OpenRoIS", code="Gripper"),
    name="gripper",
    function=ComponentFunction.ACTUATION,
    command_profiles=[
        CommandMessageProfile(
            name="grip",
            arguments=[_parameter("force", "double")],
            results=[_parameter("held", "bool")],
        ),
        CommandMessageProfile(name="squeeze", timeout=50),
    ],
    query_profiles=[
        QueryMessageProfile(name="width", results=[_parameter("width", "double")]),
    ],
)


@component(GRIPPER_PROFILE)
class Gripper(Component):
    """A gripper that holds whatever it grips, and squeezes for ever."""

    def __init__(self) -> None:
        self.forces: list[float] = []

    @invoke("grip")
    async def grip(self, force: float) -> dict[str, object]:
        self.forces.append(force)
        return {"held": force > 0}

    @invoke("squeeze")
    async def squeeze(self) -> None:
        await asyncio.Event().wait()

    @query("width")
    async def width(self) -> dict[str, object]:
        return {"width": 0.08}


# ---------------------------------------------------------------------------
# A peer of an engine, without a socket
# ---------------------------------------------------------------------------


class Peer:
    """A session of an engine, driven through the JSON-RPC framing.

    Every reply goes through :func:`openrois.engine.jsonrpc.answer`, as it would on a
    connection, and every notification is recorded with its params as JSON.
    """

    def __init__(self, engine: Engine, *, trusted: bool = False) -> None:
        self.engine = engine
        self.notifications: list[tuple[str, dict[str, Any]]] = []
        self.session = engine.open_session(self._notify, trusted=trusted)
        self._next_id = 0

    def _notify(self, method: str, params: BaseModel) -> None:
        self.notifications.append((method, params.model_dump(mode="json")))

    async def reply(self, method: str, params: Any = None) -> dict[str, Any]:
        """Send one request and return the whole reply."""
        self._next_id += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            message["params"] = params
        raw = await answer(self.engine, self.session, json.dumps(message))
        assert raw is not None
        reply: dict[str, Any] = json.loads(raw)
        return reply

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        """Send one request and return its result."""
        reply = await self.reply(method, params)
        assert "result" in reply, reply
        result: dict[str, Any] = reply["result"]
        return result

    def sent(self, method: str) -> list[dict[str, Any]]:
        """The params of every notification of one method, in order."""
        return [params for name, params in self.notifications if name == method]

    def status_of(self, command_id: str) -> str | None:
        """The status the completed notification of a command reported, if it came."""
        for params in self.sent("rois.command.completed"):
            if params["command_id"] == command_id:
                status: str = params["status"]
                return status
        return None

    async def completed(self, command_id: str, timeout: float = 2.0) -> str:
        """Wait for the completed notification of a command and return its status."""
        await wait_until(lambda: self.status_of(command_id) is not None, timeout)
        status = self.status_of(command_id)
        assert status is not None
        return status

    async def close(self) -> None:
        await self.engine.close_session(self.session)


def unit(
    ref: str,
    command_type: str,
    command_id: str,
    delay_time: int | None = None,
    **arguments: str,
) -> dict[str, Any]:
    """One command of an execute, as the wire writes it."""
    return {
        "component_ref": ref,
        "command_type": command_type,
        "command_id": command_id,
        "arguments": [
            {"name": name, "data_type_ref": "", "value": value}
            for name, value in arguments.items()
        ],
        "delay_time": delay_time,
    }


# ---------------------------------------------------------------------------
# Gateways, clients and adapters on real sockets
# ---------------------------------------------------------------------------


@dataclass
class Gateway:
    """A running gateway: the engine and the server in front of it."""

    engine: Engine
    server: WsServer

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.server.port}"

    @classmethod
    async def start(cls, engine_id: str = "gateway") -> Gateway:
        engine = Engine(engine_id)
        server = WsServer(engine, child_timeout=CHILD_TIMEOUT)
        await engine.start()
        await server.start("127.0.0.1", 0)
        return cls(engine, server)

    async def stop(self) -> None:
        await self.server.stop()
        await self.engine.stop()


class RpcClient:
    """A JSON-RPC client that matches replies by id and records every message."""

    def __init__(self, connection: ClientConnection) -> None:
        self.connection = connection
        self.messages: list[dict[str, Any]] = []
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
                self.messages.append(message)
                future = self._pending.pop(message.get("id"), None) if "id" in message else None
                if future is not None:
                    future.set_result(message)
        except ConnectionClosed:
            pass

    def send(self, method: str, params: Any = None) -> asyncio.Future[dict[str, Any]]:
        """Send a request and return a future for the whole reply."""
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[self._next_id] = future
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        message["params"] = params if params is not None else {}
        asyncio.ensure_future(self.connection.send(json.dumps(message)))
        return future

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        """Send a request and return its result."""
        reply = await asyncio.wait_for(self.send(method, params), timeout=2.0)
        assert "result" in reply, reply
        result: dict[str, Any] = reply["result"]
        return result

    def sent(self, method: str) -> list[dict[str, Any]]:
        """The params of every notification of one method received so far."""
        return [m["params"] for m in self.messages if m.get("method") == method]

    async def notification(
        self, method: str, match: Callable[[dict[str, Any]], bool] = lambda _: True
    ) -> dict[str, Any]:
        """Wait for a notification of one method whose params match, and return them."""
        await wait_until(lambda: any(match(p) for p in self.sent(method)))
        return next(p for p in self.sent(method) if match(p))

    async def completed(self, command_id: str) -> str:
        """Wait for the completed notification of a command and return its status."""
        params = await self.notification(
            "rois.command.completed", lambda p: p["command_id"] == command_id
        )
        status: str = params["status"]
        return status

    async def close(self) -> None:
        await self.connection.close()
        await self._reader


@dataclass
class Adapter:
    """A running adapter: its engine, its components and the WsClient task."""

    engine: Engine
    components: dict[str, Component]
    task: asyncio.Task[None]

    async def stop(self) -> None:
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


async def start_adapter(
    url: str,
    gateway: Gateway | None,
    engine_id: str = "robot",
    components: Mapping[str, Component] | None = None,
) -> Adapter:
    """Start an adapter and wait until the gateway has added it, when one is given."""
    engine = Engine(engine_id)
    hosted: dict[str, Component] = (
        dict(components) if components is not None else {"navigation": Navigation()}
    )
    for name, hosted_component in hosted.items():
        engine.add_component(name, hosted_component)
    task = asyncio.create_task(WsClient(engine, url).run_async())
    if gateway is not None:
        await wait_until(lambda: engine_id in gateway.engine.child_engine_ids())
    return Adapter(engine, hosted, task)


class FakeChild:
    """A child engine written by hand, for discovery replies an adapter never sends."""

    def __init__(self, connection: ClientConnection) -> None:
        self.connection = connection

    @classmethod
    async def connect(cls, gateway: Gateway) -> FakeChild:
        return cls(await connect(f"{gateway.url}/adapter"))

    async def request(self) -> dict[str, Any]:
        """The next request from the gateway."""
        message: dict[str, Any] = json.loads(
            await asyncio.wait_for(self.connection.recv(), timeout=2.0)
        )
        return message

    async def reply(self, request: dict[str, Any], result: dict[str, Any]) -> None:
        """Answer one request of the gateway."""
        message = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        await self.connection.send(json.dumps(message))

    async def answer_profile(
        self,
        engine_id: str,
        refs: list[str] | None = None,
        sub_engine_ids: tuple[str, ...] = (),
    ) -> None:
        """Answer the gateway's get_profile with sensing components, one by default."""
        request = await self.request()
        assert request["method"] == "rois.system.get_profile"
        component_ids = refs if refs is not None else [f"{engine_id}/camera"]
        camera = PERSON_DETECTION_PROFILE.model_copy(update={"name": "camera"})
        await self.reply(
            request,
            {
                "return_code": "OK",
                "profile": {
                    "identifier": {"authority": "OpenRoIS", "code": engine_id},
                    "sub_profiles": [
                        {"identifier": {"authority": "OpenRoIS", "code": sub}}
                        for sub in sub_engine_ids
                    ],
                    "component_ids": component_ids,
                },
                "component_profiles": {
                    ref: camera.model_dump(mode="json") for ref in component_ids
                },
            },
        )

    async def closed(self) -> tuple[int | None, str | None]:
        """Wait until the gateway closes the connection, and return code and reason."""
        await asyncio.wait_for(self.connection.wait_closed(), timeout=2.0)
        return self.connection.close_code, self.connection.close_reason
