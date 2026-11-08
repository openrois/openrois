"""Component profiles condensed to what an agent needs to drive a component."""

from __future__ import annotations

from typing import Any

from openrois.interfaces import HRIComponentProfile
from openrois.interfaces.profiles import ParameterProfile, RoISIdentifierType


def type_name(identifier: RoISIdentifierType) -> str:
    """A component type as ``authority::code``, or the code alone without an authority."""
    if identifier.authority:
        return f"{identifier.authority}::{identifier.code}"
    return identifier.code


def engine_of(component_ref: str) -> str:
    """The engine that hosts a component: its ref without the last segment."""
    head, _, _ = component_ref.rpartition("/")
    return head


def _field(profile: ParameterProfile, *, with_read_only: bool = False) -> dict[str, Any]:
    field: dict[str, Any] = {"name": profile.name, "type": profile.data_type_ref.code}
    if profile.default_value is not None:
        field["default"] = profile.default_value
    if profile.description:
        field["description"] = profile.description
    if with_read_only and profile.read_only:
        field["read_only"] = True
    return field


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
    return {
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
            _field(parameter, with_read_only=True) for parameter in profile.parameter_profiles
        ],
    }
