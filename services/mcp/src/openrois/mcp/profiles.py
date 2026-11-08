"""Component profiles condensed to what an agent needs to drive a component."""

from __future__ import annotations

from typing import Any

from openrois.interfaces import HRIComponentProfile, Parameter
from openrois.interfaces.profiles import ParameterProfile, RoISIdentifierType

from openrois.mcp import values

#: What describe says about parameters, which an agent could take for per-call defaults.
PARAMETERS_NOTE = (
    "initial_value is a parameter's value before anyone set it. Parameters stay on the "
    "component between sessions, so set every parameter a command reads before each start"
)


def type_name(identifier: RoISIdentifierType) -> str:
    """A component type as ``authority::code``, or the code alone without an authority."""
    if identifier.authority:
        return f"{identifier.authority}::{identifier.code}"
    return identifier.code


def engine_of(component_ref: str) -> str:
    """The engine that hosts a component: its ref without the last segment."""
    head, _, _ = component_ref.rpartition("/")
    return head


def _field(profile: ParameterProfile, *, parameter: bool = False) -> dict[str, Any]:
    """One argument, result or parameter.

    A parameter's default_value is the value the component starts with, which any session
    can change, so it reads initial_value, as JSON, rather than default.
    """
    field: dict[str, Any] = {"name": profile.name, "type": profile.data_type_ref.code}
    if profile.default_value is not None:
        if parameter:
            field["initial_value"] = _decoded(profile.data_type_ref.code, profile.default_value)
        else:
            field["default"] = profile.default_value
    if profile.description:
        field["description"] = profile.description
    if parameter and profile.read_only:
        field["read_only"] = True
    return field


def _decoded(data_type: str, text: str) -> Any:
    """A RoIS value string as JSON, or the string when it does not fit its type."""
    return values.decode([Parameter(name="value", data_type_ref=data_type, value=text)])[0]["value"]


def summary(component_ref: str, profile: HRIComponentProfile) -> dict[str, Any]:
    """One line of a component list: who it is and what it offers, by name only."""
    return {
        "ref": component_ref,
        "type": type_name(profile.identifier),
        "engine": engine_of(component_ref),
        "function": profile.function.value if profile.function else None,
        "commands": [command.name for command in profile.command_profiles],
        "queries": [query.name for query in profile.query_profiles],
        "events": [event.name for event in profile.event_profiles],
    }


def describe(component_ref: str, profile: HRIComponentProfile) -> dict[str, Any]:
    """Everything an agent needs to call a component, without the XML detail."""
    commands = []
    for command in profile.command_profiles:
        entry: dict[str, Any] = {
            "name": command.name,
            "arguments": [_field(argument) for argument in command.arguments],
            "results": [_field(result) for result in command.results],
        }
        if command.timeout is not None:
            entry["timeout_ms"] = command.timeout
        commands.append(entry)
    described: dict[str, Any] = {
        "ref": component_ref,
        "type": type_name(profile.identifier),
        "name": profile.name,
        "engine": engine_of(component_ref),
        "function": profile.function.value if profile.function else None,
        "needs_exclusive_bind": profile.function is not None
        and profile.function.value == "actuation",
        "commands": commands,
        "queries": [
            {
                "name": query.name,
                "arguments": [_field(argument) for argument in query.arguments],
                "results": [_field(result) for result in query.results],
            }
            for query in profile.query_profiles
        ],
        "events": [
            {
                "name": event.name,
                "arguments": [_field(argument) for argument in event.arguments],
                "results": [_field(result) for result in event.results],
            }
            for event in profile.event_profiles
        ],
        "parameters": [
            _field(parameter, parameter=True) for parameter in profile.parameter_profiles
        ],
    }
    if profile.parameter_profiles:
        described["parameters_note"] = PARAMETERS_NOTE
    return described
