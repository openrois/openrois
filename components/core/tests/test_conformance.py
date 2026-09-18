"""The conformance suite against the reference and example components."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import Result, ReturnCode
from openrois_components.common import MockSystemInformation
from openrois_components_core import component, invoke, meta_from_decorators, query, results
from openrois_components_core.conformance import Finding, assert_conformant, conformance_report
from openrois_core import Engine, EventEmitter

ROOT = Path(__file__).resolve().parents[3]


def engine_with(*handlers: Any) -> Engine:
    engine = Engine(engine_id="test", platform="test")
    engine.component_registry.set_emitter(EventEmitter(asyncio.get_running_loop()))
    for handler in handlers:
        meta = meta_from_decorators(type(handler))
        engine.register_component(meta.ref, handler, meta)
    return engine


async def test_common_components_conform() -> None:
    await assert_conformant(engine_with(MockSystemInformation()))


async def test_avatar_adapter_conforms() -> None:
    sys.path.insert(0, str(ROOT / "examples" / "avatar-adapter"))
    import avatar_adapter

    engine = engine_with(*(cls({}) for cls in avatar_adapter.COMPONENT_CLASSES))
    await assert_conformant(engine)


async def test_mock_adapter_conforms() -> None:
    sys.path.insert(0, str(ROOT / "examples" / "mock-adapter"))
    import mock_adapter

    engine = engine_with(*(cls({}) for cls in mock_adapter.COMPONENT_CLASSES))
    await assert_conformant(engine)


@component("Navigation")
class SloppyNavigation:
    """Breaks three rules: no component_status, an invented query, a failing query."""

    @query("battery")
    async def battery(self) -> list[Result]:
        raise RuntimeError("no battery")

    @invoke("execute")
    async def execute(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        return InvokeResponse(return_code=ReturnCode.OK, command_id="x")


async def test_findings_name_the_component_and_the_rule() -> None:
    report = await conformance_report(engine_with(SloppyNavigation()))
    rules = {(f.component, f.rule) for f in report}
    assert ("Navigation", "rois_common") in rules
    assert ("Navigation", "normative_names") in rules
    assert ("Navigation", "query") in rules
    assert all(isinstance(f, Finding) and str(f).startswith("Navigation: ") for f in report)


async def test_assert_conformant_lists_every_finding() -> None:
    try:
        await assert_conformant(engine_with(SloppyNavigation()))
    except AssertionError as exc:
        assert "rois_common" in str(exc) and "normative_names" in str(exc)
    else:
        raise AssertionError("expected findings")


async def test_a_conformant_component_has_no_findings() -> None:
    @component("SpeechSynthesis", parameters=[{"name": "speech_text", "data_type_ref": "string"}])
    class Speech:
        @query("component_status")
        async def status(self) -> list[Result]:
            return results.status("READY")

        @invoke("set_parameter")
        async def set_parameter(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
            return InvokeResponse(return_code=ReturnCode.OK, command_id="")

        @invoke("start")
        async def start(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
            return InvokeResponse(return_code=ReturnCode.OK, command_id="s")

        @invoke("stop")
        async def stop(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
            return InvokeResponse(return_code=ReturnCode.OK, command_id="")

        @invoke("suspend")
        async def suspend(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
            return InvokeResponse(return_code=ReturnCode.OK, command_id="")

        @invoke("resume")
        async def resume(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
            return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    assert await conformance_report(engine_with(Speech())) == []
