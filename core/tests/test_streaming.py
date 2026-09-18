"""The Streaming Interface control plane: rois.stream.* onto a streaming component."""

from __future__ import annotations

import asyncio
from typing import Any

import websockets
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

from openrois_core import Engine, WsClient, WsServer

from .test_ws_roundtrip import Application


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
    # The public id is qualified by the component ref: components pick their own
    # ids, and two adapters behind one gateway may pick the same one.
    assert connected["stream_id"] == "VideoStreaming/v1"
    stream_id = connected["stream_id"]
    assert connected["results"] == [
        {"name": "media_url", "data_type_ref": "string", "value": "http://cam/whep/v1"},
    ]

    status = await engine.dispatch("rois.stream.query_stream_status", {"stream_id": stream_id})
    assert status == {"return_code": "OK", "status": "STREAMING_RUNNING"}

    async def op(name: str) -> str:
        answer = await engine.dispatch(f"rois.stream.{name}", {"stream_id": stream_id})
        return str(answer["return_code"])

    assert await op("suspend_stream") == "OK"
    assert sink.envelopes[-1].event_type == "notify_stream_status"
    assert sink.envelopes[-1].stream_status == "STREAMING_SUSPENDED"
    # The event names the stream by its public id, not the component's local one.
    assert sink.envelopes[-1].payload[0].value == stream_id
    assert await op("resume_stream") == "OK"
    resumed = await engine.dispatch("rois.stream.query_stream_status", {"stream_id": stream_id})
    assert resumed["status"] == "STREAMING_RESUMED"

    assert await op("disconnect_stream") == "OK"
    gone = await engine.dispatch("rois.stream.query_stream_status", {"stream_id": stream_id})
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
    connected = await engine.dispatch(
        "rois.stream.connect_stream", {"component_ref": "VideoStreaming"}, sink, "app",
    )
    await engine.dispatch("rois.stream.disconnect_stream", {"stream_id": connected["stream_id"]})
    seen = len(sink.envelopes)
    video.status["v1"] = "STREAMING_RUNNING"
    await video.parent.emit_async(  # type: ignore[attr-defined]
        "VideoStreaming", "notify_stream_status",
        [Result(name="stream_id", data_type_ref="string", value="v1")],
    )
    await asyncio.sleep(0)
    assert len(sink.envelopes) == seen


async def test_a_stream_belongs_to_the_client_that_connected_it(make_engine, sink) -> None:
    engine, video = await with_video(make_engine)
    connected = await engine.dispatch(
        "rois.stream.connect_stream", {"component_ref": "VideoStreaming"}, sink, "alice",
    )
    stream_id = connected["stream_id"]
    params = {"stream_id": stream_id}
    for method in ("suspend_stream", "resume_stream", "disconnect_stream", "query_stream_status"):
        answer = await engine.dispatch(f"rois.stream.{method}", params, None, "bob")
        assert answer["return_code"] == "UNSUPPORTED", method
    assert video.calls == ["connect_stream"]
    mine = await engine.dispatch("rois.stream.query_stream_status", params, None, "alice")
    assert mine["status"] == "STREAMING_RUNNING"


async def test_streams_of_two_adapters_do_not_collide_at_the_gateway(sink) -> None:
    """Both adapters answer connect_stream with the same local id "v1"."""
    gateway = Engine(engine_id="gateway", enforce_bindings=True)
    server = WsServer(gateway)
    await server.start("127.0.0.1", 0)
    port = server._server.sockets[0].getsockname()[1]
    videos: dict[str, FakeVideo] = {}
    tasks = []
    for engine_id in ("robot_a", "robot_b"):
        adapter = Engine(engine_id=engine_id, platform="fake")
        videos[engine_id] = FakeVideo()
        meta = meta_from_decorators(FakeVideo)
        adapter.register_component("VideoStreaming", videos[engine_id], meta)
        client = WsClient(adapter, f"ws://127.0.0.1:{port}")
        tasks.append(asyncio.create_task(client._run_async()))
    for _ in range(100):
        if len(gateway.get_sub_engines()) == 2:
            break
        await asyncio.sleep(0.05)
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws_a, \
                websockets.connect(f"ws://127.0.0.1:{port}") as ws_b:
            alice, bob = Application(ws_a), Application(ws_b)
            connect = "rois.stream.connect_stream"
            a = await alice.call(connect, component_ref="robot_a/VideoStreaming")
            b = await alice.call(connect, component_ref="robot_b/VideoStreaming")
            assert a["stream_id"] == "robot_a/VideoStreaming/v1"
            assert b["stream_id"] == "robot_b/VideoStreaming/v1"

            assert await alice.code("rois.stream.suspend_stream", stream_id=a["stream_id"]) == "OK"
            status = await alice.next_notification("rois.stream.notify_status")
            assert status["params"]["stream_id"] == a["stream_id"]
            assert status["params"]["status"] == "STREAMING_SUSPENDED"
            other = await alice.call("rois.stream.query_stream_status", stream_id=b["stream_id"])
            assert other["status"] == "STREAMING_RUNNING"
            assert videos["robot_b"].calls == ["connect_stream"]

            # Bob neither owns the streams nor hears about them.
            resumed = await bob.code("rois.stream.resume_stream", stream_id=a["stream_id"])
            assert resumed == "UNSUPPORTED"
            heard = [n for n in bob.notifications if n["method"] == "rois.stream.notify_status"]
            assert heard == []
        # Alice is gone: her streams are disconnected at the components.
        for _ in range(100):
            if all(v.calls[-1] == "disconnect_stream" for v in videos.values()):
                break
            await asyncio.sleep(0.05)
        assert videos["robot_a"].calls == ["connect_stream", "suspend_stream", "disconnect_stream"]
        assert videos["robot_b"].calls == ["connect_stream", "disconnect_stream"]
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        await server.stop()
