"""What belongs to which client: subscriptions, the search condition, and scoped bind_any."""

from __future__ import annotations

import asyncio

from .conftest import RecordingSink


async def test_only_the_subscriber_can_unsubscribe(make_engine, sink) -> None:
    engine, nav = make_engine()
    sub = await engine.dispatch(
        "rois.event.subscribe", {"component_ref": "Navigation", "event_type": "reached_target"},
        sink, "alice",
    )
    subscribe_id = sub["subscribe_id"]
    params = {"subscribe_id": subscribe_id}
    bob = await engine.dispatch("rois.event.unsubscribe", params, None, "bob")
    assert bob["return_code"] == "UNSUPPORTED"
    await nav.arrive("kitchen")
    await asyncio.sleep(0)
    assert [e.event_type for e in sink.envelopes] == ["reached_target"]
    alice = await engine.dispatch("rois.event.unsubscribe", params, None, "alice")
    assert alice["return_code"] == "OK"
    await nav.arrive("hall")
    await asyncio.sleep(0)
    assert len(sink.envelopes) == 1


async def test_search_applies_the_condition(make_engine) -> None:
    engine, _ = make_engine()

    async def search(condition: str) -> list[str]:
        answer = await engine.dispatch("rois.command.search", {"condition": condition})
        return list(answer["component_ref_list"])

    assert await search("") == ["SystemInformation", "Navigation"]
    assert await search("navigation") == ["Navigation"]
    assert await search("Sys*") == ["SystemInformation"]
    assert await search("*Info*") == ["SystemInformation"]
    assert await search("Gripper") == []


async def test_bind_any_stays_within_the_visible_scope(make_engine) -> None:
    engine, _ = make_engine()
    visible = lambda ref: ref.startswith("Nav")  # noqa: E731
    outside = await engine.dispatch(
        "rois.command.bind_any", {"condition": "SystemInformation"}, None, "alice", visible=visible,
    )
    assert outside["return_code"] == "UNSUPPORTED"
    inside = await engine.dispatch(
        "rois.command.bind_any", {"condition": ""}, None, "alice", visible=visible,
    )
    assert inside == {"return_code": "OK", "component_ref": "Navigation"}


async def test_release_all_forgets_the_subscription_owner(make_engine) -> None:
    engine, _ = make_engine()
    sink = RecordingSink()
    sub = await engine.dispatch(
        "rois.event.subscribe", {"component_ref": "Navigation", "event_type": "reached_target"},
        sink, "alice",
    )
    engine.release_all("alice")
    # Nobody owns it any more, so the cleanup path of any caller may drop it.
    params = {"subscribe_id": sub["subscribe_id"]}
    gone = await engine.dispatch("rois.event.unsubscribe", params, None, "bob")
    assert gone["return_code"] == "OK"
