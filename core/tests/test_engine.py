"""Engine dispatch through the Component Contract, with local components."""

from __future__ import annotations

import asyncio
from typing import Any

from openrois.interfaces.bus import ComponentContract
from openrois.interfaces.hri import ReturnCode
from openrois_components_core import results

from openrois_core.engine import ComponentRegistry, Engine, SubEngine

PARAMS = [{"name": "target_positions", "data_type_ref": "string[]", "value": '["kitchen"]'}]
NAV = {"component_ref": "Navigation"}


async def call(
    engine: Engine,
    method: str,
    params: dict[str, Any] | None = None,
    sink: Any = None,
    client: str | None = None,
) -> dict[str, Any]:
    return await engine.dispatch(method, params or {}, sink, client)


async def test_registry_and_sub_engine_satisfy_the_contract() -> None:
    loop = asyncio.get_running_loop()
    assert isinstance(ComponentRegistry(), ComponentContract)
    assert isinstance(SubEngine(None, loop), ComponentContract)


async def test_connect_and_search(make_engine) -> None:
    engine, _ = make_engine()
    assert await call(engine, "rois.system.connect") == {"return_code": "OK"}
    assert await call(engine, "rois.command.search") == {
        "return_code": "OK",
        "component_ref_list": ["SystemInformation", "Navigation"],
    }


async def test_get_profile_lists_components_with_their_messages(make_engine) -> None:
    engine, _ = make_engine()
    profile = (await call(engine, "rois.system.get_profile"))["profile"]
    assert profile["identifier"]["code"] == "robot_1"
    assert profile["platform"] == "fake"
    assert profile["component_ids"] == ["SystemInformation", "Navigation"]
    nav = profile["component_profiles"][1]
    assert nav["function"] == "actuation"
    assert [q["name"] for q in nav["query_profiles"]] == ["component_status"]
    assert {c["name"] for c in nav["command_profiles"]} == {"set_parameter", "execute", "stop"}
    assert [e["name"] for e in nav["event_profiles"]] == ["reached_target"]


async def test_query_returns_typed_results(make_engine) -> None:
    engine, _ = make_engine()
    result = await call(
        engine, "rois.query.query",
        {"component_ref": "SystemInformation", "query_type": "robot_position"},
    )
    assert result["return_code"] == "OK"
    assert [r["name"] for r in result["results"]] == ["x", "y", "theta"]


async def test_query_unknown_component_or_type_is_unsupported(make_engine) -> None:
    engine, _ = make_engine()
    missing = await call(engine, "rois.query.query", {"component_ref": "Nope", "query_type": "x"})
    assert missing["return_code"] == "UNSUPPORTED"
    wrong = await call(engine, "rois.query.query", {**NAV, "query_type": "robot_position"})
    assert wrong["return_code"] == "UNSUPPORTED"


async def test_execute_passes_parameters_as_dicts(make_engine, sink) -> None:
    engine, nav = make_engine()
    result = await call(
        engine, "rois.command.execute",
        {**NAV, "command_type": "execute", "parameters": PARAMS}, sink, "client-a",
    )
    assert result["return_code"] == "OK"
    assert result["command_id"] == "cmd-nav"
    assert nav.received == [PARAMS]


async def test_execute_accepts_a_command_unit_list(make_engine, sink) -> None:
    engine, nav = make_engine()
    unit = {**NAV, "command_type": "execute", "command_id": "cmd-7", "arguments": PARAMS}
    result = await call(
        engine, "rois.command.execute", {**NAV, "command_unit_list": [unit]}, sink, "client-a",
    )
    assert result["return_code"] == "OK"
    assert nav.received == [PARAMS]


async def test_execute_skips_malformed_parameters(make_engine, sink) -> None:
    engine, nav = make_engine()
    params = [{"junk": 1}, *PARAMS]
    result = await call(
        engine, "rois.command.execute",
        {**NAV, "command_type": "execute", "parameters": params}, sink, "client-a",
    )
    assert result["return_code"] == "OK"
    assert nav.received == [PARAMS]


async def test_unknown_command_type_is_a_bad_parameter(make_engine, sink) -> None:
    engine, nav = make_engine()
    result = await call(engine, "rois.command.execute", {**NAV, "command_type": "fly"}, sink, "c")
    assert result["return_code"] == "BAD_PARAMETER"
    assert nav.received == []


async def test_handler_exception_becomes_error_code(make_engine, sink) -> None:
    engine, _ = make_engine()
    result = await call(engine, "rois.command.execute", {**NAV, "command_type": "stop"}, sink, "c")
    assert result["return_code"] == "ERROR"


async def test_set_parameter_reaches_the_component(make_engine) -> None:
    engine, nav = make_engine()
    result = await call(engine, "rois.command.set_parameter", {**NAV, "parameters": PARAMS})
    assert result["return_code"] == "OK"
    assert nav.parameters == PARAMS


async def test_bind_is_exclusive_when_enforced(make_engine, sink) -> None:
    engine, _ = make_engine(enforce_bindings=True)

    async def bind(client: str) -> str:
        return (await call(engine, "rois.command.bind", NAV, None, client))["return_code"]

    assert await bind("a") == "OK"
    assert await bind("b") == "OUT_OF_RESOURCES"
    blocked = await call(
        engine, "rois.command.execute", {**NAV, "command_type": "execute"}, sink, "b",
    )
    assert blocked["return_code"] == "OUT_OF_RESOURCES"
    released = await call(engine, "rois.command.release", NAV, None, "a")
    assert released["return_code"] == "OK"
    assert await bind("b") == "OK"


async def test_sensing_components_never_require_a_binding(make_engine) -> None:
    engine, _ = make_engine(enforce_bindings=True)
    ref = {"component_ref": "SystemInformation"}
    assert (await call(engine, "rois.command.bind", ref, None, "a"))["return_code"] == "OK"
    assert (await call(engine, "rois.command.bind", ref, None, "b"))["return_code"] == "OK"


async def test_release_all_frees_a_clients_bindings(make_engine) -> None:
    engine, _ = make_engine(enforce_bindings=True)
    await call(engine, "rois.command.bind", NAV, None, "a")
    engine.release_all("a")
    assert (await call(engine, "rois.command.bind", NAV, None, "b"))["return_code"] == "OK"


async def test_subscribe_delivers_events_to_the_sink(make_engine, sink) -> None:
    engine, nav = make_engine()
    result = await call(
        engine, "rois.event.subscribe", {**NAV, "event_type": "reached_target"}, sink, "a",
    )
    assert result["return_code"] == "OK"
    subscribe_id = result["subscribe_id"]
    assert subscribe_id
    assert nav.subscribed == 1

    await nav.arrive("kitchen")
    assert len(sink.envelopes) == 1
    envelope = sink.envelopes[0]
    assert envelope.subscribe_id == subscribe_id
    assert envelope.component_ref == "Navigation"
    assert envelope.event_type == "reached_target"
    assert [r.name for r in envelope.payload] == ["target", "is_final_target"]

    gone = await call(engine, "rois.event.unsubscribe", {"subscribe_id": subscribe_id})
    assert gone["return_code"] == "OK"
    await nav.arrive("desk")
    assert len(sink.envelopes) == 1


async def test_emit_from_a_thread_reaches_the_loop(make_engine, sink) -> None:
    engine, nav = make_engine()
    await call(engine, "rois.event.subscribe", {**NAV, "event_type": "reached_target"}, sink, "a")
    payload = results.reached_target(target="x", is_final_target=True)
    await asyncio.to_thread(nav.parent.emit, "Navigation", "reached_target", payload)
    await asyncio.wait_for(sink.arrived.wait(), timeout=2)
    assert sink.envelopes[0].event_type == "reached_target"


async def test_subscribe_without_a_sink_fails(make_engine) -> None:
    engine, _ = make_engine()
    result = await call(engine, "rois.event.subscribe", {**NAV, "event_type": "reached_target"})
    assert result == {"return_code": "ERROR", "subscribe_id": ""}


async def test_subscribe_unknown_event_is_unsupported(make_engine, sink) -> None:
    engine, _ = make_engine()
    result = await call(engine, "rois.event.subscribe", {**NAV, "event_type": "nope"}, sink)
    assert result["return_code"] == "UNSUPPORTED"


async def test_unsubscribe_unknown_id_is_ok(make_engine) -> None:
    engine, _ = make_engine()
    result = await call(engine, "rois.event.unsubscribe", {"subscribe_id": "gone"})
    assert result["return_code"] == "OK"


async def test_unknown_method_is_unsupported(make_engine) -> None:
    engine, _ = make_engine()
    result = await call(engine, "rois.stream.connect_stream")
    assert result["return_code"] == ReturnCode.UNSUPPORTED.value
