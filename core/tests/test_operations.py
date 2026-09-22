"""The Command, System, and Event operations added on top of the basic dispatch:
bind_any, get_parameter, get_command_result, get_error_detail, get_event_detail,
and the completed and notify_error notifications."""

from __future__ import annotations

from typing import Any

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import Result, ReturnCode
from openrois_components_core import component, invoke, meta_from_decorators, query, results

from openrois_core import Engine

NAV = {"component_ref": "Navigation"}
PARAMS = [{"name": "target_positions", "data_type_ref": "string[]", "value": '["kitchen"]'}]


async def call(engine: Engine, method: str, params: dict[str, Any] | None = None,
               sink: Any = None, client: str | None = None) -> dict[str, Any]:
    return await engine.dispatch(method, params or {}, sink, client)


@component("Reaction", function="actuation")
class SelfDescribingReaction:
    """A component that answers get_parameter itself."""

    @query("get_parameter")
    async def get_parameter(self) -> list[Result]:
        return [Result(name="reaction_ref", data_type_ref="string", value="smile")]

    @invoke("execute")
    async def execute(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        return InvokeResponse(
            return_code=ReturnCode.OK, command_id="cmd-react",
            results=results.status("BUSY"),
        )


async def test_bind_any_picks_a_free_matching_component(make_engine) -> None:
    engine, _ = make_engine(enforce_bindings=True)
    first = await call(engine, "rois.command.bind_any", {"condition": "navigation"}, None, "a")
    assert first == {"return_code": "OK", "component_ref": "Navigation"}
    second = await call(engine, "rois.command.bind_any", {"condition": "Navigation"}, None, "b")
    assert second["return_code"] == "OUT_OF_RESOURCES"
    none = await call(engine, "rois.command.bind_any", {"condition": "Speech"}, None, "b")
    assert none["return_code"] == "UNSUPPORTED"


async def test_get_parameter_returns_what_set_parameter_stored(make_engine) -> None:
    engine, _ = make_engine()
    assert (await call(engine, "rois.command.get_parameter", NAV))["results"] == []
    await call(engine, "rois.command.set_parameter", {**NAV, "parameters": PARAMS})
    everything = await call(engine, "rois.command.get_parameter", NAV)
    assert everything == {"return_code": "OK", "results": PARAMS}
    filtered = await call(engine, "rois.command.get_parameter", {**NAV, "names": ["other"]})
    assert filtered["results"] == []
    unknown = await call(engine, "rois.command.get_parameter", {"component_ref": "Nope"})
    assert unknown["return_code"] == "UNSUPPORTED"


async def test_get_parameter_prefers_the_components_own_query(make_engine) -> None:
    engine, _ = make_engine()
    handler = SelfDescribingReaction()
    engine.register_component("Reaction", handler, meta_from_decorators(SelfDescribingReaction))
    result = await call(engine, "rois.command.get_parameter", {"component_ref": "Reaction"})
    expected = [{"name": "reaction_ref", "data_type_ref": "string", "value": "smile"}]
    assert result["results"] == expected


async def test_get_command_result_returns_the_immediate_results(make_engine, sink) -> None:
    engine, _ = make_engine()
    engine.register_component(
        "Reaction", SelfDescribingReaction(), meta_from_decorators(SelfDescribingReaction),
    )
    executed = await call(
        engine, "rois.command.execute",
        {"component_ref": "Reaction", "command_type": "execute"}, sink, "a",
    )
    assert executed["command_id"] == "cmd-react"
    result = await call(engine, "rois.command.get_command_result", {"command_id": "cmd-react"})
    assert result["return_code"] == "OK"
    assert result["results"][0]["name"] == "status"
    missing = await call(engine, "rois.command.get_command_result", {"command_id": "nope"})
    assert missing["return_code"] == "UNSUPPORTED"


async def test_completion_reaches_the_caller_and_updates_the_result(make_engine, sink) -> None:
    engine, nav = make_engine()
    executed = await call(
        engine, "rois.command.execute", {**NAV, "command_type": "execute"}, sink, "a",
    )
    command_id = executed["command_id"]
    done = results.reached_target(target="kitchen", is_final_target=True)
    await nav.parent.complete_async(command_id, "OK", done)

    assert len(sink.envelopes) == 1
    envelope = sink.envelopes[0]
    assert envelope.event_type == "completed"
    assert envelope.completed_status == "OK"
    assert [r.name for r in envelope.payload] == ["command_id", "target", "is_final_target"]

    result = await call(engine, "rois.command.get_command_result", {"command_id": command_id})
    assert [r["name"] for r in result["results"]] == ["target", "is_final_target"]

    # A second completion for the same command has nobody to reach.
    await nav.parent.complete_async(command_id, "OK", [])
    assert len(sink.envelopes) == 1


async def test_completion_from_a_thread(make_engine, sink) -> None:
    import asyncio

    engine, nav = make_engine()
    executed = await call(
        engine, "rois.command.execute", {**NAV, "command_type": "execute"}, sink, "a",
    )
    await asyncio.to_thread(nav.parent.complete, executed["command_id"], "ABORT")
    await asyncio.wait_for(sink.arrived.wait(), timeout=2)
    assert sink.envelopes[0].completed_status == "ABORT"


async def test_handler_failure_notifies_the_caller(make_engine, sink) -> None:
    engine, _ = make_engine()
    result = await call(engine, "rois.command.execute", {**NAV, "command_type": "stop"}, sink, "a")
    assert result["return_code"] == "ERROR"
    assert len(sink.envelopes) == 1
    error = sink.envelopes[0]
    assert error.event_type == "notify_error"
    assert error.error_type == "COMPONENT_INTERNAL_ERROR"

    detail = await call(engine, "rois.system.get_error_detail", {"error_id": error.event_id})
    assert detail["return_code"] == "OK"
    assert detail["error_type"] == "COMPONENT_INTERNAL_ERROR"
    assert any(r["name"] == "message" and "Navigation" in r["value"] for r in detail["results"])
    missing = await call(engine, "rois.system.get_error_detail", {"error_id": "nope"})
    assert missing["return_code"] == "UNSUPPORTED"


async def test_get_event_detail_returns_a_delivered_event(make_engine, sink) -> None:
    engine, nav = make_engine()
    await call(engine, "rois.event.subscribe", {**NAV, "event_type": "reached_target"}, sink, "a")
    await nav.arrive("kitchen")
    event_id = sink.envelopes[0].event_id
    detail = await call(engine, "rois.event.get_event_detail", {"event_id": event_id})
    assert detail["return_code"] == "OK"
    assert detail["event_type"] == "reached_target"
    assert detail["component_ref"] == "Navigation"
    assert [r["name"] for r in detail["results"]] == ["target", "is_final_target"]
    missing = await call(engine, "rois.event.get_event_detail", {"event_id": "nope"})
    assert missing["return_code"] == "UNSUPPORTED"
