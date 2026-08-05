"""Tests for the EventEmitter."""

from __future__ import annotations

import asyncio
import json

import pytest
from openrois.interfaces.hri import Result

from openrois.sdk.events import EventEmitter


@pytest.fixture
async def emitter():
    """Create an EventEmitter with a mock ws_send that records messages."""
    sent_messages: list[str] = []

    async def ws_send(msg: str) -> None:
        sent_messages.append(msg)

    loop = asyncio.get_running_loop()
    em = EventEmitter(ws_send, loop)
    em._sent_messages = sent_messages  # type: ignore[attr-defined]
    return em


async def test_add_subscription_returns_id(emitter):
    """add_subscription returns a unique subscribe_id."""
    sid1 = emitter.add_subscription("Navigation", "reached_target")
    sid2 = emitter.add_subscription("ObjectDetection", "object_detected")
    assert sid1 != sid2
    assert sid1.startswith("sub-")
    assert sid2.startswith("sub-")


async def test_remove_subscription(emitter):
    """remove_subscription removes by subscribe_id."""
    sid = emitter.add_subscription("Navigation", "reached_target")
    assert emitter.remove_subscription(sid) is True
    assert emitter.remove_subscription(sid) is False  # already removed


async def test_remove_all_subscriptions(emitter):
    """remove_all_subscriptions clears all."""
    emitter.add_subscription("Navigation", "reached_target")
    emitter.add_subscription("ObjectDetection", "object_detected")
    emitter.remove_all_subscriptions()
    assert not emitter.has_subscribers("Navigation", "reached_target")
    assert not emitter.has_subscribers("ObjectDetection", "object_detected")


async def test_has_subscribers(emitter):
    """has_subscribers returns True only for matching component/event."""
    emitter.add_subscription("Navigation", "reached_target")
    assert emitter.has_subscribers("Navigation", "reached_target")
    assert not emitter.has_subscribers("Navigation", "object_detected")
    assert not emitter.has_subscribers("ObjectDetection", "reached_target")


async def test_emit_sends_to_subscribers(emitter):
    """emit sends a notification to each matching subscriber."""
    sid1 = emitter.add_subscription("ObjectDetection", "object_detected")
    sid2 = emitter.add_subscription("ObjectDetection", "object_detected")

    results = [Result(name="object_id", data_type_ref="string", value="0")]
    emitter.emit("ObjectDetection", "object_detected", results)

    # Give the scheduled coroutines time to run.
    await asyncio.sleep(0.05)

    assert len(emitter._sent_messages) == 2  # type: ignore[attr-defined]
    for msg in emitter._sent_messages:  # type: ignore[attr-defined]
        parsed = json.loads(msg)
        assert parsed["method"] == "rois.event.notification"
        assert parsed["params"]["event_type"] == "object_detected"
        assert parsed["params"]["subscribe_id"] in (sid1, sid2)


async def test_emit_noop_without_subscribers(emitter):
    """emit does nothing if nobody is subscribed."""
    results = [Result(name="x", data_type_ref="float", value="1.0")]
    emitter.emit("Navigation", "reached_target", results)
    await asyncio.sleep(0.05)
    assert len(emitter._sent_messages) == 0  # type: ignore[attr-defined]


async def test_emit_only_matches_correct_event_type(emitter):
    """emit only sends to subscribers of the exact event type."""
    emitter.add_subscription("ObjectDetection", "object_detected")
    emitter.add_subscription("ObjectDetection", "object_lost")

    results = [Result(name="object_id", data_type_ref="string", value="0")]
    emitter.emit("ObjectDetection", "object_detected", results)
    await asyncio.sleep(0.05)

    assert len(emitter._sent_messages) == 1  # type: ignore[attr-defined]


async def test_emit_async_sends_to_subscribers(emitter):
    """emit_async sends notifications from async context."""
    emitter.add_subscription("Navigation", "reached_target")
    results = [Result(name="target", data_type_ref="string", value="desk")]
    await emitter.emit_async("Navigation", "reached_target", results)
    assert len(emitter._sent_messages) == 1  # type: ignore[attr-defined]
    parsed = json.loads(emitter._sent_messages[0])  # type: ignore[attr-defined]
    assert parsed["params"]["event_type"] == "reached_target"
