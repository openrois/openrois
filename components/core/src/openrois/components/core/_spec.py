"""What a decorated component class declares, checked against its profile.

``@component`` builds a ComponentSpec when a class is defined: which method handles
each command, query and event, the hook for new parameter values, and the profile the
engine serves for the class. A handler that does not match the profile fails here, at
class definition, so a typo cannot advertise a message the profile does not define.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from openrois.interfaces.profiles import CommandMessageProfile, HRIComponentProfile

type HandlerKind = Literal["command", "query", "event", "set_parameter"]

# The attribute the method decorators set on the functions they mark.
HANDLER_ATTRIBUTE = "__rois_handler__"

# The engine answers these itself, so a component never handles them.
ENGINE_COMMANDS = frozenset({"set_parameter"})
ENGINE_QUERIES = frozenset({"component_status"})


@dataclass(frozen=True, slots=True)
class Handler:
    """The message a method handles, set on the method by a decorator."""

    kind: HandlerKind
    name: str


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    """The messages a component class handles and the profile it serves.

    Attributes:
        declared: The profile the class declares, usually a profile constant.
        served: The declared profile with only the messages the class answers: the
            commands, queries and events it has handlers for, ``stop`` when it handles
            ``start``, and ``component_status``, which the engine answers. Every
            parameter of the declared profile stays.
        commands: The method that handles each command, by command name.
        queries: The method that handles each query, by query name.
        events: The method that runs on a new subscription, by event name.
        set_parameter_hook: The method that applies new parameter values, if any.
    """

    declared: HRIComponentProfile
    served: HRIComponentProfile
    commands: Mapping[str, str]
    queries: Mapping[str, str]
    events: Mapping[str, str]
    set_parameter_hook: str | None


def build_spec(cls: type, profile: HRIComponentProfile) -> ComponentSpec:
    """Collect the handlers of a class and check them against its profile.

    Raises:
        TypeError: A handler is not a coroutine function or has parameters its message
            does not define.
        ValueError: A handler names a message the profile does not define, a message the
            engine answers itself, or a message another handler already handles.
    """
    owner = f"{cls.__qualname__}"
    kind_of_type = f"{profile.identifier.authority} {profile.identifier.code}".strip()
    defined: dict[HandlerKind, set[str]] = {
        "command": {m.name for m in profile.command_profiles},
        "query": {m.name for m in profile.query_profiles},
        "event": {m.name for m in profile.event_profiles},
    }
    tables: dict[HandlerKind, dict[str, str]] = {"command": {}, "query": {}, "event": {}}
    hook: str | None = None

    for attribute in dir(cls):
        method = getattr(cls, attribute, None)
        handler = getattr(method, HANDLER_ATTRIBUTE, None)
        if not isinstance(handler, Handler):
            continue
        where = f"{owner}.{attribute}"
        if not inspect.iscoroutinefunction(method):
            raise TypeError(f"{where} must be an async def")
        parameters = list(inspect.signature(method).parameters.values())[1:]

        if handler.kind == "set_parameter":
            if not profile.parameter_profiles:
                raise ValueError(f"{where} is an @on_set_parameter hook, but the profile "
                                 f"{kind_of_type} declares no parameters")
            if hook is not None:
                raise ValueError(f"{owner} has two @on_set_parameter hooks: {hook} and "
                                 f"{attribute}")
            if len(parameters) != 1:
                raise TypeError(f"{where} must take one argument, the new values")
            hook = attribute
            continue

        if handler.kind == "command" and handler.name in ENGINE_COMMANDS:
            raise ValueError(f"{where} handles {handler.name}, which the engine runs itself. "
                             "Apply new parameter values in an @on_set_parameter hook")
        if handler.kind == "query" and handler.name in ENGINE_QUERIES:
            raise ValueError(f"{where} answers {handler.name}, which the engine answers "
                             "itself")
        if handler.name not in defined[handler.kind]:
            raise ValueError(f"{where} handles the {handler.kind} {handler.name!r}, which the "
                             f"profile {kind_of_type} does not define")
        table = tables[handler.kind]
        if handler.name in table:
            raise ValueError(f"{owner}.{table[handler.name]} and {where} both handle the "
                             f"{handler.kind} {handler.name!r}")
        if handler.kind == "command":
            message = next(m for m in profile.command_profiles if m.name == handler.name)
            _check_command_parameters(where, message, parameters)
        elif parameters:
            raise TypeError(f"{where} must take no arguments besides self")
        table[handler.name] = attribute

    commands, queries, events = tables["command"], tables["query"], tables["event"]
    served = profile.model_copy(
        update={
            "command_profiles": [
                m
                for m in profile.command_profiles
                if m.name in commands or (m.name == "stop" and "start" in commands)
            ],
            "query_profiles": [
                m for m in profile.query_profiles if m.name in queries or m.name in ENGINE_QUERIES
            ],
            "event_profiles": [m for m in profile.event_profiles if m.name in events],
        }
    )
    return ComponentSpec(
        declared=profile,
        served=served,
        commands=MappingProxyType(commands),
        queries=MappingProxyType(queries),
        events=MappingProxyType(events),
        set_parameter_hook=hook,
    )


def _check_command_parameters(
    where: str,
    message: CommandMessageProfile,
    parameters: list[inspect.Parameter],
) -> None:
    """A command handler takes the arguments of its command by name, and nothing else."""
    arguments = {a.name for a in message.arguments}
    for parameter in parameters:
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            continue
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            raise TypeError(f"{where} cannot take *{parameter.name}: arguments arrive by name")
        if parameter.name not in arguments:
            raise TypeError(f"{where} takes {parameter.name!r}, which the command "
                            f"{message.name!r} does not define as an argument")
