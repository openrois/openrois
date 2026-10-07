"""ChildEngine on its own, with the messages of a child played by hand."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openrois.interfaces.service import NotifyEventParams

from openrois.engine import ChildEngine


class Wire:
    """The connection of a ChildEngine: what it sent, and replies played back to it."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.child = ChildEngine(self.send, request_timeout=0.5)

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    def reply(self, result: dict[str, Any]) -> None:
        self.child.handle({"jsonrpc": "2.0", "id": self.sent[-1]["id"], "result": result})

    async def discover(self) -> None:
        discovery = asyncio.create_task(self.child.discover())
        await asyncio.sleep(0)
        self.reply(
            {
                "return_code": "OK",
                "profile": {"identifier": {"code": "cam"}, "component_ids": []},
            }
        )
        await discovery


async def test_a_subscription_whose_caller_left_after_the_reply_is_ended() -> None:
    wire = Wire()
    await wire.discover()
    delivered: list[NotifyEventParams] = []
    subscribe = asyncio.create_task(
        wire.child.subscribe("cam/camera", "person_detected", delivered.append)
    )
    await asyncio.sleep(0)
    wire.reply({"return_code": "OK", "subscribe_id": "cam/sub-1"})
    # The caller is cancelled after the reply arrived, before it could pass it on.
    subscribe.cancel()
    await asyncio.gather(subscribe, return_exceptions=True)
    await asyncio.sleep(0.01)
    assert wire.sent[-1]["method"] == "rois.event.unsubscribe"
    assert wire.sent[-1]["params"] == {"subscribe_id": "cam/sub-1"}


async def test_a_reply_after_the_caller_left_ends_the_subscription() -> None:
    wire = Wire()
    await wire.discover()
    subscribe = asyncio.create_task(wire.child.subscribe("cam/camera", "person_detected", print))
    await asyncio.sleep(0)
    request_id = wire.sent[-1]["id"]
    subscribe.cancel()
    await asyncio.gather(subscribe, return_exceptions=True)
    late = {"return_code": "OK", "subscribe_id": "cam/sub-2"}
    wire.child.handle({"jsonrpc": "2.0", "id": request_id, "result": late})
    await asyncio.sleep(0.01)
    assert wire.sent[-1]["params"] == {"subscribe_id": "cam/sub-2"}


async def test_a_late_reply_leaves_a_held_subscription_alone() -> None:
    wire = Wire()
    await wire.discover()
    held = asyncio.create_task(wire.child.subscribe("cam/camera", "person_detected", print))
    await asyncio.sleep(0)
    wire.reply({"return_code": "OK", "subscribe_id": "cam/sub-1"})
    assert (await held).subscribe_id == "cam/sub-1"
    late = asyncio.create_task(wire.child.subscribe("cam/camera", "person_detected", print))
    await asyncio.sleep(0)
    request_id = wire.sent[-1]["id"]
    late.cancel()
    await asyncio.gather(late, return_exceptions=True)
    # A buggy child answers the abandoned request with the id of the held subscription.
    reused = {"return_code": "OK", "subscribe_id": "cam/sub-1"}
    wire.child.handle({"jsonrpc": "2.0", "id": request_id, "result": reused})
    await asyncio.sleep(0.01)
    assert all(m["method"] != "rois.event.unsubscribe" for m in wire.sent)


async def test_detach_answers_every_waiting_request_with_error() -> None:
    wire = Wire()
    await wire.discover()
    query = asyncio.create_task(wire.child.query("cam/camera", "component_status"))
    await asyncio.sleep(0)
    wire.child.detach()
    assert (await query).return_code.value == "ERROR"
    assert (await wire.child.query("cam/camera", "component_status")).return_code.value == "ERROR"
