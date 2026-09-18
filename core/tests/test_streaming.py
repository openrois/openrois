"""The Streaming Interface control plane: rois.stream.* onto a streaming component."""

from __future__ import annotations

import asyncio
from typing import Any

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import Result, ReturnCode
from openrois_components_core import (
    component,
    invoke,
    meta_from_decorators,
    query,
    results,
    subscribe,
)

from openrois_core import Engine


@component("VideoStreaming", function="function")
class FakeVideo:
    def __init__(self) -> None:
        self.status: dict[str, str] = {}
        self.calls: list[str] = []

    @query("component_status")
    async def component_status(self) -> list[Result]:
        return results.status("READY")

    @invoke("connect_stream")
    async def connect_stream(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        self.calls.append("connect_stream")
        self.status["v1"] = "STREAMING_RUNNING"
        return InvokeResponse(return_code=ReturnCode.OK, command_id="v1", results=[
            Result(name="stream_id", data_type_ref="string", value="v1"),
            Result(name="media_url", data_type_ref="string", value="http://cam/whep/v1"),
        ])

    async def _transition(
        self, parameters: list[dict[str, Any]], status: str, name: str,
    ) -> InvokeResponse:
        self.calls.append(name)
        stream_id = next(p["value"] for p in parameters if p["name"] == "stream_id")
        if stream_id not in self.status:
            return InvokeResponse(return_code=ReturnCode.BAD_PARAMETER, command_id="")
        self.status[stream_id] = status
        await self.parent.emit_async(  # type: ignore[attr-defined]
            "VideoStreaming", "notify_stream_status",
            [Result(name="stream_id", data_type_ref="string", value=stream_id),
             Result(name="status", data_type_ref="Stream_Status", value=status)],
        )
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("suspend_stream")
    async def suspend_stream(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        return await self._transition(parameters, "STREAMING_SUSPENDED", "suspend_stream")

    @invoke("resume_stream")
    async def resume_stream(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        return await self._transition(parameters, "STREAMING_RESUMED", "resume_stream")

    @invoke("disconnect_stream")
    async def disconnect_stream(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        return await self._transition(parameters, "STREAMING_NOT_CONNECTED", "disconnect_stream")

    @query("get_stream_status")
    async def get_stream_status(self, stream_id: str) -> list[Result]:
        status = self.status.get(stream_id, "STREAMING_NOT_CONNECTED")
        return [Result(name="status", data_type_ref="Stream_Status", value=status)]

    @subscribe("notify_stream_status")
    async def on_status(self) -> None:
        pass


async def with_video(make_engine) -> tuple[Engine, FakeVideo]:
    engine, _ = make_engine()
    video = FakeVideo()
    engine.register_component("VideoStreaming", video, meta_from_decorators(FakeVideo))
    return engine, video


async def test_stream_lifecycle_through_the_engine(make_engine, sink) -> None:
    engine, video = await with_video(make_engine)
    connected = await engine.dispatch(
        "rois.stream.connect_stream", {"component_ref": "VideoStreaming"}, sink, "app",
    )
    assert connected["return_code"] == "OK"
    assert connected["stream_id"] == "v1"
    assert connected["results"] == [
        {"name": "media_url", "data_type_ref": "string", "value": "http://cam/whep/v1"},
    ]

    status = await engine.dispatch("rois.stream.query_stream_status", {"stream_id": "v1"})
    assert status == {"return_code": "OK", "status": "STREAMING_RUNNING"}

    async def op(name: str) -> str:
        answer = await engine.dispatch(f"rois.stream.{name}", {"stream_id": "v1"})
        return str(answer["return_code"])

    assert await op("suspend_stream") == "OK"
    assert sink.envelopes[-1].event_type == "notify_stream_status"
    assert sink.envelopes[-1].stream_status == "STREAMING_SUSPENDED"
    assert await op("resume_stream") == "OK"
    resumed = await engine.dispatch("rois.stream.query_stream_status", {"stream_id": "v1"})
    assert resumed["status"] == "STREAMING_RESUMED"

    assert await op("disconnect_stream") == "OK"
    gone = await engine.dispatch("rois.stream.query_stream_status", {"stream_id": "v1"})
    assert gone["return_code"] == "UNSUPPORTED"
    assert video.calls == ["connect_stream", "suspend_stream", "resume_stream", "disconnect_stream"]


async def test_unknown_stream_is_unsupported(make_engine) -> None:
    engine, _ = await with_video(make_engine)
    missing = await engine.dispatch("rois.stream.suspend_stream", {"stream_id": "nope"})
    assert missing["return_code"] == "UNSUPPORTED"
    wrong = await engine.dispatch("rois.stream.connect_stream", {"component_ref": "Navigation"})
    assert wrong["return_code"] == "UNSUPPORTED"


async def test_status_events_stop_after_disconnect(make_engine, sink) -> None:
    engine, video = await with_video(make_engine)
    await engine.dispatch(
        "rois.stream.connect_stream", {"component_ref": "VideoStreaming"}, sink, "app",
    )
    await engine.dispatch("rois.stream.disconnect_stream", {"stream_id": "v1"})
    seen = len(sink.envelopes)
    video.status["v1"] = "STREAMING_RUNNING"
    await video.parent.emit_async(  # type: ignore[attr-defined]
        "VideoStreaming", "notify_stream_status",
        [Result(name="stream_id", data_type_ref="string", value="v1")],
    )
    await asyncio.sleep(0)
    assert len(sink.envelopes) == seen
