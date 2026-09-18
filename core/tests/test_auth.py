"""Authentication at the upgrade and authorization per operation."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import jwt
import pytest
import websockets

from openrois_core import Engine, WsClient, WsServer
from openrois_core.auth import AuthConfig, AuthError, Principal, token_from

from .conftest import build_engine

SECRET = "a-test-secret-of-at-least-thirty-two-bytes"
CONFIG = AuthConfig(key=SECRET, issuer="openrois-test")


def make_token(roles: list[str], scope: list[str] | None = None, **extra: Any) -> str:
    claims: dict[str, Any] = {
        "sub": "someone",
        "iss": "openrois-test",
        "exp": int(time.time()) + 300,
        "roles": roles,
        **extra,
    }
    if scope is not None:
        claims["scope"] = scope
    return jwt.encode(claims, SECRET, algorithm="HS256")


# -- Unit --


def test_decode_valid_token() -> None:
    principal = CONFIG.decode(make_token(["operator"], ["robot_1/*"]))
    assert principal.subject == "someone"
    assert principal.roles == {"operator"}
    assert principal.scope == ("robot_1/*",)


def test_decode_rejects_bad_signature_expiry_issuer_and_unknown_roles() -> None:
    with pytest.raises(AuthError):
        other_key = "another-secret-of-at-least-thirty-two-bytes"
        claims = {"sub": "x", "exp": time.time() + 60, "roles": ["operator"]}
        CONFIG.decode(jwt.encode(claims, other_key, algorithm="HS256"))
    with pytest.raises(AuthError):
        CONFIG.decode(make_token(["operator"], exp=int(time.time()) - 3600))
    with pytest.raises(AuthError):
        CONFIG.decode(make_token(["operator"], iss="someone-else"))
    with pytest.raises(AuthError):
        CONFIG.decode(make_token(["ceo"]))


def test_roles_map_to_operations() -> None:
    viewer = Principal("v", frozenset({"viewer"}))
    operator = Principal("o", frozenset({"operator"}))
    admin = Principal("a", frozenset({"administrator"}))
    adapter = Principal("r", frozenset({"adapter"}))
    assert viewer.may_call("rois.query.query") and not viewer.may_call("rois.command.execute")
    assert operator.may_call("rois.command.execute")
    assert admin.may_call("rois.command.bind_any")
    assert not adapter.may_call("rois.system.connect") and adapter.is_adapter


def test_scope_matches_component_refs() -> None:
    scoped = Principal("s", frozenset({"operator"}), ("robot_1/*", "lab/SystemInformation"))
    assert scoped.may_see("robot_1/Navigation")
    assert scoped.may_see("lab/SystemInformation")
    assert not scoped.may_see("robot_2/Navigation")
    assert Principal("all", frozenset({"viewer"})).may_see("anything/Anywhere")


def test_token_from_header_or_query() -> None:
    assert token_from({"Authorization": "Bearer abc"}, "/") == "abc"
    assert token_from({}, "/?token=xyz") == "xyz"
    assert token_from({}, "/adapter?access_token=q") == "q"
    assert token_from({}, "/") is None


# -- Through the gateway --


class Application:
    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self._next = 0
        self.notifications: list[dict[str, Any]] = []

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        self._next += 1
        await self._ws.send(json.dumps(
            {"jsonrpc": "2.0", "id": self._next, "method": method, "params": params},
        ))
        while True:
            msg = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=5))
            if msg.get("id") == self._next:
                result: dict[str, Any] = msg["result"]
                return result
            self.notifications.append(msg)


@pytest.fixture
async def secured() -> AsyncIterator[int]:
    """A gateway that requires tokens, with one adapter connected using an adapter token."""
    gateway = Engine(engine_id="gateway", enforce_bindings=True)
    server = WsServer(gateway, auth=CONFIG)
    await server.start("127.0.0.1", 0)
    port = server._server.sockets[0].getsockname()[1]

    adapter_engine, _ = build_engine(engine_id="robot_1")
    client = WsClient(adapter_engine, f"ws://127.0.0.1:{port}", token=make_token(["adapter"]))
    task = asyncio.create_task(client._run_async())
    for _ in range(100):
        if gateway.get_sub_engines():
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("adapter with a valid token never registered")

    yield port

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await server.stop()


async def test_connection_without_a_token_is_refused(secured) -> None:
    with pytest.raises(websockets.exceptions.InvalidStatus) as excinfo:
        async with websockets.connect(f"ws://127.0.0.1:{secured}"):
            pass
    assert excinfo.value.response.status_code == 401


async def test_adapter_without_the_adapter_role_is_refused(secured) -> None:
    headers = {"Authorization": f"Bearer {make_token(['operator'])}"}
    with pytest.raises(websockets.exceptions.InvalidStatus) as excinfo:
        async with websockets.connect(
            f"ws://127.0.0.1:{secured}/adapter", additional_headers=headers,
        ):
            pass
    assert excinfo.value.response.status_code == 403


async def test_viewer_can_read_but_not_command(secured) -> None:
    url = f"ws://127.0.0.1:{secured}/?token={make_token(['viewer'])}"
    async with websockets.connect(url) as ws:
        app = Application(ws)
        assert (await app.call("rois.command.search"))["component_ref_list"] == [
            "robot_1/SystemInformation", "robot_1/Navigation",
        ]
        query = await app.call(
            "rois.query.query", component_ref="robot_1/SystemInformation",
            query_type="robot_position",
        )
        assert query["return_code"] == "OK"
        denied = await app.call("rois.command.bind", component_ref="robot_1/Navigation")
        assert denied["return_code"] == "ERROR"
        error = next(n for n in app.notifications if n["method"] == "rois.system.notify_error")
        assert "rois.command.bind" in error["params"]["message"]
        # The refusal is on record, like any other engine error.
        error_id = error["params"]["error_id"]
        detail = await app.call("rois.system.get_error_detail", error_id=error_id)
        assert detail["return_code"] == "OK"
        assert "rois.command.bind" in json.dumps(detail)


async def test_operator_can_command_within_scope(secured) -> None:
    headers = {"Authorization": f"Bearer {make_token(['operator'], ['robot_1/Nav*'])}"}
    async with websockets.connect(f"ws://127.0.0.1:{secured}", additional_headers=headers) as ws:
        app = Application(ws)
        # Scope hides what the operator may not see.
        found = (await app.call("rois.command.search"))["component_ref_list"]
        assert found == ["robot_1/Navigation"]
        profile = (await app.call("rois.system.get_profile"))["profile"]
        assert profile["component_ids"] == ["robot_1/Navigation"]
        bound = await app.call("rois.command.bind", component_ref="robot_1/Navigation")
        assert bound["return_code"] == "OK"
        executed = await app.call(
            "rois.command.execute", component_ref="robot_1/Navigation", command_type="execute",
        )
        assert executed["return_code"] == "OK"
        outside = await app.call(
            "rois.query.query", component_ref="robot_1/SystemInformation",
            query_type="robot_position",
        )
        assert outside["return_code"] == "ERROR"
        # bind_any cannot reach past the scope either, whatever the condition says.
        await app.call("rois.command.release", component_ref="robot_1/Navigation")
        sneaky = await app.call("rois.command.bind_any", condition="SystemInformation")
        assert sneaky["return_code"] == "UNSUPPORTED"
        allowed = await app.call("rois.command.bind_any", condition="")
        assert allowed == {"return_code": "OK", "component_ref": "robot_1/Navigation"}
