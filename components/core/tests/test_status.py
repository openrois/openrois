"""Tests for resources, raised statuses, the engine status and message arguments."""

from __future__ import annotations

import threading

import pytest
from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components import (
    AUDIO_STREAMING_PROFILE,
    NAVIGATION_PROFILE,
    SYSTEM_INFORMATION_PROFILE,
)
from openrois.interfaces.hri import Argument

from openrois.components.core import Component, Resource, component, query, subscribe
from tests._support import RecordingBinding, RecordingResourceBinding


class Link(Resource):
    """A shared connection that opens and closes nothing."""


@component(NAVIGATION_PROFILE)
class Navigation(Component):
    def __init__(self, link: Link | None = None) -> None:
        if link is not None:
            self.link = self.uses(link)


@component(AUDIO_STREAMING_PROFILE)
class Microphone(Component):
    def __init__(self) -> None:
        self.watched: list[str | None] = []

    @query("get_stream_status")
    async def get_stream_status(self, stream_id: str) -> dict[str, object]:
        return {"status": "STREAMING_RUNNING"}

    @subscribe("notify_stream_status")
    async def notify_stream_status(self, stream_id: str | None = None) -> None:
        self.watched.append(stream_id)


@component(SYSTEM_INFORMATION_PROFILE)
class SystemInformation(Component):
    @query("engine_status")
    async def engine_status(self) -> dict[str, object]:
        return {"status": self.engine_state()}


# -- Resources ---------------------------------------------------------------------------


def test_uses_records_the_resources_of_a_component_and_returns_them() -> None:
    link = Link()
    navigation = Navigation(link)
    assert navigation.link is link
    assert list(navigation.rois_resources()) == [link]
    assert list(Navigation().rois_resources()) == []


def test_a_resource_reports_its_status_to_the_engine_once_bound() -> None:
    link = Link()
    link.raise_status(ComponentStatus.WARNING, "No robot yet.")
    binding = RecordingResourceBinding()
    link.rois_bind(binding)
    # A status raised before the engine bound the resource is reported on bind.
    assert binding.raised == [(ComponentStatus.WARNING, "No robot yet.")]
    link.clear_status()
    link.raise_status(ComponentStatus.ERROR, "The robot is gone.")
    assert binding.raised[1:] == [None, (ComponentStatus.ERROR, "The robot is gone.")]


async def test_open_and_close_default_to_nothing() -> None:
    link = Link()
    await link.open()
    await link.close()


@pytest.mark.parametrize("status", [ComponentStatus.READY, ComponentStatus.BUSY])
def test_only_warning_and_error_can_be_raised(status: ComponentStatus) -> None:
    navigation = Navigation()
    navigation.rois_bind(RecordingBinding())
    with pytest.raises(ValueError, match="WARNING or ERROR"):
        navigation.raise_status(status, "")
    with pytest.raises(ValueError, match="WARNING or ERROR"):
        Link().raise_status(status, "")


# -- Raised statuses ---------------------------------------------------------------------


def test_a_component_raises_and_clears_its_status_from_any_thread() -> None:
    navigation = Navigation()
    binding = RecordingBinding()
    navigation.rois_bind(binding)
    thread = threading.Thread(
        target=navigation.raise_status, args=(ComponentStatus.WARNING, "The battery is low.")
    )
    thread.start()
    thread.join()
    navigation.clear_status()
    assert binding.raised == [(ComponentStatus.WARNING, "The battery is low."), None]


def test_raising_needs_an_engine() -> None:
    with pytest.raises(RuntimeError, match="No engine"):
        Navigation().raise_status(ComponentStatus.ERROR, "")


async def test_a_component_reads_the_status_of_its_engine() -> None:
    information = SystemInformation()
    binding = RecordingBinding(ref="robot/system_info", engine=ComponentStatus.WARNING)
    information.rois_bind(binding)
    [status] = await information.rois_query("engine_status")
    assert status.value == "WARNING"


# -- Arguments of queries and events ------------------------------------------------------


def _argument(name: str, value: str) -> Argument:
    return Argument(name=name, data_type_ref="String", value=value)


async def test_a_query_handler_takes_its_arguments_by_name() -> None:
    microphone = Microphone()
    microphone.rois_bind(RecordingBinding(ref="studio/microphone"))
    results = await microphone.rois_query("get_stream_status", [_argument("stream_id", "a1")])
    assert [r.name for r in results] == ["status"]
    with pytest.raises(ValueError, match="no argument"):
        await microphone.rois_query("get_stream_status", [_argument("track", "a1")])


async def test_a_subscribe_hook_takes_the_arguments_of_the_subscription() -> None:
    microphone = Microphone()
    microphone.rois_bind(RecordingBinding(ref="studio/microphone"))
    await microphone.rois_subscribed("notify_stream_status", [_argument("stream_id", "a1")])
    await microphone.rois_subscribed("notify_stream_status")
    assert microphone.watched == ["a1", None]


def test_emit_names_the_argument_values_an_event_concerns() -> None:
    microphone = Microphone()
    binding = RecordingBinding(ref="studio/microphone")
    microphone.rois_bind(binding)
    microphone.emit(
        "notify_stream_status", concerning={"stream_id": "a1"}, status="STREAMING_RUNNING"
    )
    microphone.emit("notify_stream_status", status="STREAMING_RUNNING")
    assert binding.concerns == [{"stream_id": "a1"}, {}]
    with pytest.raises(ValueError, match="no argument"):
        microphone.emit("notify_stream_status", concerning={"track": "a1"})


def test_a_handler_must_take_arguments_its_message_defines() -> None:
    with pytest.raises(TypeError, match="does not define"):

        @component(AUDIO_STREAMING_PROFILE)
        class Wrong(Component):
            @query("get_stream_status")
            async def get_stream_status(self, track: str) -> None:
                return None
