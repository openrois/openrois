"""The JSON-RPC framing: protocol faults, notifications, and the order of the outbox."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from openrois.interfaces.service import CompletedParams, CompletedStatus
from pydantic import BaseModel

from openrois.engine import Engine
from openrois.engine.jsonrpc import Outbox, answer, notification
from tests._support import Peer


@pytest.fixture
def peer() -> Peer:
    return Peer(Engine("robot"))


async def raw_reply(peer: Peer, raw: str) -> dict[str, Any] | None:
    reply = await answer(peer.engine, peer.session, raw)
    return None if reply is None else json.loads(reply)


async def test_json_that_does_not_parse_is_a_parse_error_with_a_null_id(peer: Peer) -> None:
    reply = await raw_reply(peer, "{not json")
    assert reply == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32700, "message": "Parse error: invalid JSON"},
    }


async def test_json_nested_too_deep_is_a_parse_error(peer: Peer) -> None:
    reply = await raw_reply(peer, "[" * 100_000)
    assert reply is not None
    assert reply["error"]["code"] == -32700


@pytest.mark.parametrize(
    ("message", "request_id"),
    [
        ({"jsonrpc": "1.0", "id": 7, "method": "rois.system.connect"}, 7),
        ({"jsonrpc": "2.0", "id": 7, "method": 42}, 7),
        ({"jsonrpc": "2.0", "id": True, "method": "rois.system.connect"}, None),
        ([1, 2, 3], None),
    ],
)
async def test_a_message_that_is_not_a_request_is_an_invalid_request(
    peer: Peer, message: Any, request_id: Any
) -> None:
    reply = await raw_reply(peer, json.dumps(message))
    assert reply is not None
    assert reply["id"] == request_id
    assert reply["error"]["code"] == -32600


@pytest.mark.parametrize("method", ["rois.system.reboot", "rois.stream.open"])
async def test_a_method_outside_the_catalog_is_method_not_found(peer: Peer, method: str) -> None:
    reply = await peer.reply(method, {})
    assert reply["error"] == {"code": -32601, "message": f"Method not found: {method}"}


async def test_params_that_fail_the_catalog_model_are_invalid_params(peer: Peer) -> None:
    reply = await peer.reply("rois.command.bind", {"component": "robot/navigation"})
    assert reply["error"]["code"] == -32602
    assert reply["error"]["message"] == "Invalid params for rois.command.bind"
    paths = {issue["path"] for issue in reply["error"]["data"]}
    assert paths == {"component_ref", "component"}


async def test_positional_params_are_invalid_params(peer: Peer) -> None:
    reply = await peer.reply("rois.command.bind", ["robot/navigation"])
    assert reply["error"]["code"] == -32602


async def test_a_method_without_params_takes_its_defaults(peer: Peer) -> None:
    reply = await peer.reply("rois.system.get_profile")
    assert reply["result"]["return_code"] == "OK"


async def test_a_notification_gets_no_reply(peer: Peer) -> None:
    message = {"jsonrpc": "2.0", "method": "rois.system.connect", "params": {}}
    assert await raw_reply(peer, json.dumps(message)) is None


async def test_an_engine_failure_is_an_internal_error(
    peer: Peer, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*args: Any) -> BaseModel:
        raise RuntimeError("boom")

    monkeypatch.setattr(peer.engine, "handle", fail)
    reply = await peer.reply("rois.system.connect", {})
    assert reply["error"] == {"code": -32603, "message": "Internal error"}


async def test_the_outbox_sends_in_the_order_messages_were_put() -> None:
    sent: list[str] = []
    gate = asyncio.Event()

    async def send(message: str) -> None:
        await gate.wait()
        sent.append(message)

    outbox = Outbox(send)
    outbox.put("reply")
    outbox.notify(
        "rois.command.completed", CompletedParams(command_id="c1", status=CompletedStatus.OK)
    )
    gate.set()
    await asyncio.sleep(0.01)
    await outbox.close()
    assert sent == [
        "reply",
        notification(
            "rois.command.completed", CompletedParams(command_id="c1", status=CompletedStatus.OK)
        ),
    ]
    assert json.loads(sent[1]) == {
        "jsonrpc": "2.0",
        "method": "rois.command.completed",
        "params": {"command_id": "c1", "status": "OK"},
    }


async def test_the_outbox_keeps_sending_after_a_failed_send() -> None:
    sent: list[str] = []

    async def send(message: str) -> None:
        if message == "first":
            raise RuntimeError("socket gone")
        sent.append(message)

    outbox = Outbox(send)
    outbox.put("first")
    outbox.put("second")
    await asyncio.sleep(0.01)
    await outbox.close()
    assert sent == ["second"]
