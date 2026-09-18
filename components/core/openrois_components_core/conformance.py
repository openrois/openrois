"""Conformance checks for an engine and the components it hosts.

The checks drive an ``Engine`` through the same ``dispatch()`` that the
WebSocket layers use, so they validate what an application would see. Point
them at any adapter's engine, local or through a gateway, and every finding
names the component and the rule it broke. Use ``assert_conformant`` in a
test, or ``conformance_report`` to inspect the findings.

    from openrois_components_core.conformance import assert_conformant

    async def test_my_adapter():
        engine, _ = build_my_engine()
        await assert_conformant(engine)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from openrois.interfaces.hri import Result, ReturnCode
from openrois.interfaces.profiles import HRIComponentProfile, HRIEngineProfileType

# RoIS_Common: every component but SystemInformation answers component_status,
# and actuation components accept the four lifecycle commands.
COMMON_QUERY = "component_status"
COMMON_COMMANDS = ("start", "stop", "suspend", "resume")

# OpenRoIS adds these keys to profiles; they are stripped before validation.
EXTENSION_KEYS = {"function", "platform", "sub_engine_ids"}

# The 17 basic HRI Components of RoIS 2.0, with the messages OpenRoIS has typed
# models for. A basic component that declares other names is reported.
BASIC_MESSAGES: dict[str, dict[str, set[str]]] = {
    "PersonDetection": {"events": {"person_detected"}},
    "Navigation": {"events": {"reached_target"}, "queries": {"get_parameter"},
                   "commands": {"set_parameter"}},
    "Reaction": {"queries": {"get_parameter"}, "commands": {"set_parameter"}},
    "SystemInformation": {"queries": {"robot_position", "engine_status"}},
}
BASIC_COMPONENTS = {
    "PersonDetection", "PersonLocalization", "PersonIdentification", "FaceDetection",
    "FaceLocalization", "SoundDetection", "SoundLocalization", "SpeechRecognition",
    "GestureRecognition", "SpeechSynthesis", "Reaction", "Navigation", "Follow", "Move",
    "AudioStreaming", "VideoStreaming", "SystemInformation",
}


class Dispatcher(Protocol):
    async def dispatch(
        self,
        method: str,
        params: dict[str, Any],
        sink: Any = None,
        client_id: str | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Finding:
    component: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.component}: {self.rule}: {self.detail}"


class _Sink:
    def __init__(self) -> None:
        self.envelopes: list[Any] = []

    async def __call__(self, envelope: Any) -> None:
        self.envelopes.append(envelope)


def _strip_extensions(profile: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in profile.items() if k not in EXTENSION_KEYS}


def _bare(ref: str) -> str:
    return ref.split("/", 1)[1] if "/" in ref else ref


def _valid_results(results: Any) -> bool:
    if not isinstance(results, list):
        return False
    try:
        for r in results:
            Result.model_validate(r)
    except Exception:
        return False
    return True


async def conformance_report(engine: Dispatcher) -> list[Finding]:
    """Run every check and return the findings (empty when conformant)."""
    findings: list[Finding] = []
    client = "conformance"
    sink = _Sink()

    profile_result = await engine.dispatch("rois.system.get_profile", {}, sink, client)
    if profile_result.get("return_code") != ReturnCode.OK.value:
        return [Finding("engine", "get_profile", f"returned {profile_result.get('return_code')}")]
    raw_profile = profile_result.get("profile", {})

    # The engine profile itself must validate against the normative model.
    engine_profile = dict(_strip_extensions(raw_profile))
    engine_profile["component_profiles"] = [
        _strip_extensions(c) for c in raw_profile.get("component_profiles", [])
    ]
    try:
        HRIEngineProfileType.model_validate(engine_profile)
    except Exception as exc:
        findings.append(Finding("engine", "engine_profile", str(exc).splitlines()[0]))

    refs = list(raw_profile.get("component_ids", []))
    profiles = raw_profile.get("component_profiles", [])
    if len(refs) != len(profiles):
        findings.append(Finding(
            "engine", "engine_profile",
            f"{len(refs)} component_ids but {len(profiles)} component_profiles",
        ))

    search = await engine.dispatch("rois.command.search", {}, sink, client)
    if sorted(search.get("component_ref_list", [])) != sorted(refs):
        findings.append(Finding(
            "engine", "search", "search() and get_profile() list different components",
        ))

    for ref, raw in zip(refs, profiles, strict=False):
        findings.extend(await _check_component(engine, ref, raw, sink, client))
    return findings


async def _check_component(
    engine: Dispatcher,
    ref: str,
    raw: dict[str, Any],
    sink: _Sink,
    client: str,
) -> list[Finding]:
    findings: list[Finding] = []
    try:
        profile = HRIComponentProfile.model_validate(_strip_extensions(raw))
    except Exception as exc:
        return [Finding(ref, "component_profile", str(exc).splitlines()[0])]

    queries = {q.name for q in profile.query_profiles}
    commands = {c.name for c in profile.command_profiles}
    events = {e.name for e in profile.event_profiles}
    code = profile.identifier.code
    kind = _bare(code) if code else _bare(ref)

    if kind in BASIC_COMPONENTS and kind != "SystemInformation" and COMMON_QUERY not in queries:
        findings.append(Finding(ref, "rois_common", f"missing the {COMMON_QUERY} query"))
    if raw.get("function") == "actuation":
        missing = [c for c in COMMON_COMMANDS if c not in commands]
        if missing:
            findings.append(Finding(
                ref, "rois_common", f"actuation component lacks {', '.join(missing)}",
            ))
    known = BASIC_MESSAGES.get(kind)
    if known:
        for group, declared in (("queries", queries), ("commands", commands), ("events", events)):
            allowed = known.get(group, set()) | ({COMMON_QUERY} if group == "queries" else set()) \
                | (set(COMMON_COMMANDS) | {"execute"} if group == "commands" else set())
            for name in sorted(declared - allowed):
                findings.append(Finding(ref, "normative_names",
                                        f"{group[:-1]} {name!r} is not a RoIS message of {kind}"))

    # Every declared query answers with well-formed results.
    for name in sorted(queries):
        answer = await engine.dispatch(
            "rois.query.query", {"component_ref": ref, "query_type": name}, sink, client,
        )
        code_ = answer.get("return_code")
        if code_ != ReturnCode.OK.value:
            findings.append(Finding(ref, "query", f"{name} returned {code_}"))
        elif not _valid_results(answer.get("results")):
            findings.append(Finding(ref, "query", f"{name} returned malformed results"))

    # Reservations: bind and release must succeed for one client.
    if commands:
        bound = await engine.dispatch("rois.command.bind", {"component_ref": ref}, sink, client)
        if bound.get("return_code") != ReturnCode.OK.value:
            findings.append(Finding(ref, "bind", f"returned {bound.get('return_code')}"))
        # set_parameter round-trips through get_parameter with the declared defaults.
        if "set_parameter" in commands and profile.parameter_profiles:
            params = [
                {"name": p.name, "data_type_ref": p.data_type_ref.code, "value": p.default_value}
                for p in profile.parameter_profiles
            ]
            setp = await engine.dispatch(
                "rois.command.set_parameter",
                {"component_ref": ref, "parameters": params}, sink, client,
            )
            if setp.get("return_code") != ReturnCode.OK.value:
                findings.append(Finding(
                    ref, "set_parameter", f"returned {setp.get('return_code')}",
                ))
            else:
                getp = await engine.dispatch(
                    "rois.command.get_parameter", {"component_ref": ref}, sink, client,
                )
                names = {r.get("name") for r in getp.get("results", [])}
                for p in profile.parameter_profiles:
                    if p.name not in names:
                        findings.append(Finding(
                            ref, "get_parameter", f"{p.name} not returned after set_parameter",
                        ))
        released = await engine.dispatch(
            "rois.command.release", {"component_ref": ref}, sink, client,
        )
        if released.get("return_code") != ReturnCode.OK.value:
            findings.append(Finding(ref, "release", f"returned {released.get('return_code')}"))

    # Every declared event accepts a subscription and its release.
    for name in sorted(events):
        sub = await engine.dispatch(
            "rois.event.subscribe", {"component_ref": ref, "event_type": name}, sink, client,
        )
        if sub.get("return_code") != ReturnCode.OK.value or not sub.get("subscribe_id"):
            findings.append(Finding(ref, "subscribe", f"{name} returned {sub.get('return_code')}"))
            continue
        unsub = await engine.dispatch(
            "rois.event.unsubscribe", {"subscribe_id": sub["subscribe_id"]}, sink, client,
        )
        if unsub.get("return_code") != ReturnCode.OK.value:
            findings.append(Finding(
                ref, "unsubscribe", f"{name} returned {unsub.get('return_code')}",
            ))
    return findings


async def assert_conformant(engine: Dispatcher) -> None:
    """Raise AssertionError listing every finding, or return when there is none."""
    findings = await conformance_report(engine)
    if findings:
        raise AssertionError("Conformance findings:\n" + "\n".join(f"  {f}" for f in findings))
