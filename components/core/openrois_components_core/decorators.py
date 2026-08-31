"""Decorators for building OpenRoIS components.

The roboticist decorates a class with @component and its methods with
@query, @invoke, and @subscribe. The decorators set metadata attributes
on the class/method. The engine reads these attributes at registration
time to build a ComponentMeta.

Usage::

    @component("Navigation", function=ComponentFunction.ACTUATION)
    class Navigation:
        @query("waypoints")
        async def get_waypoints(self):
            return results.waypoints(self.parent._waypoints)

        @invoke("execute")
        async def navigate(self, parameters):
            ...

        @subscribe("reached_target")
        async def on_reached(self):
            ...
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

# ---------------------------------------------------------------------------
# Component function classification (RoSO ontology)
# ---------------------------------------------------------------------------

class ComponentFunction(StrEnum):
    """RoSO function classification for a component.

    Values match the RoSO Robotic Service Function Ontology classes.
    The engine derives binding enforcement from this: actuation
    components with command methods require exclusive binding.

    Source: OMG RoIS Framework 2.0-beta2, RoboticInteractionServiceComponentOntology.ttl
    """

    ACTUATION = "actuation"
    SENSING = "sensing"
    FUNCTION = "function"


# URN-to-function lookup for the 17 basic RoIS components.
# Derived from the RoIS OWL ontology (OWL.ttl). Components not in
# this dict (e.g., SystemInformation, user-defined components) default
# to None, meaning no function classification and no binding enforcement.
_BASIC_COMPONENT_FUNCTIONS: dict[str, ComponentFunction] = {
    # Actuation
    "Navigation": ComponentFunction.ACTUATION,
    "Move": ComponentFunction.ACTUATION,
    "Follow": ComponentFunction.ACTUATION,
    "Reaction": ComponentFunction.ACTUATION,
    "SpeechSynthesis": ComponentFunction.ACTUATION,
    # Sensing
    "FaceDetection": ComponentFunction.SENSING,
    "FaceLocalization": ComponentFunction.SENSING,
    "GestureRecognition": ComponentFunction.SENSING,
    "PersonDetection": ComponentFunction.SENSING,
    "PersonIdentification": ComponentFunction.SENSING,
    "PersonLocalization": ComponentFunction.SENSING,
    "SoundDetection": ComponentFunction.SENSING,
    "SoundLocalization": ComponentFunction.SENSING,
    "SpeechRecognition": ComponentFunction.SENSING,
    # Function (base, streaming)
    "AudioStreaming": ComponentFunction.FUNCTION,
    "VideoStreaming": ComponentFunction.FUNCTION,
    # SystemInformation: not in the ontology, defaults to None.
}


# ---------------------------------------------------------------------------
# Decorator metadata storage
# ---------------------------------------------------------------------------

_ROIS_COMPONENT_REF = "_rois_component_ref"
_ROIS_FUNCTION = "_rois_function"
_ROIS_PARAMETERS = "_rois_parameters"
_ROIS_QUERIES = "_rois_queries"
_ROIS_INVOKES = "_rois_invokes"
_ROIS_SUBSCRIBES = "_rois_subscribes"


def component(
    ref: str,
    *,
    function: ComponentFunction | str | None = None,
    parameters: list[dict[str, str]] | None = None,
) -> Callable[[type], type]:
    """Decorator: register a class as a handler for a component ref.

    Args:
        ref: The component ref (e.g., "Navigation").
        function: The RoSO function classification. If None, auto-derive
            from the ref using the basic component lookup table. For
            user-defined components not in the ontology, pass the
            function explicitly (e.g., function="actuation" for a
            custom manipulation component).
        parameters: Optional list of parameter profiles, each a dict
            with keys "name", "data_type_ref", and optionally
            "default_value" and "description". Matches the RoIS spec
            ParameterProfile structure. Example::

                parameters=[
                    {"name": "target_positions", "data_type_ref": "string[]"},
                    {"name": "time_limit", "data_type_ref": "int", "default_value": "0"},
                ]
    """
    def decorator(cls: type) -> type:
        # Normalize function: accept str, ComponentFunction, or None.
        if function is not None:
            fn = ComponentFunction(function) if not isinstance(function, ComponentFunction) else function
        else:
            fn = _BASIC_COMPONENT_FUNCTIONS.get(ref)
        setattr(cls, _ROIS_COMPONENT_REF, ref)
        setattr(cls, _ROIS_FUNCTION, fn)
        setattr(cls, _ROIS_PARAMETERS, parameters or [])
        # Initialize empty dicts for method routing if not already set.
        if not hasattr(cls, _ROIS_QUERIES):
            setattr(cls, _ROIS_QUERIES, {})
        if not hasattr(cls, _ROIS_INVOKES):
            setattr(cls, _ROIS_INVOKES, {})
        if not hasattr(cls, _ROIS_SUBSCRIBES):
            setattr(cls, _ROIS_SUBSCRIBES, {})
        return cls
    return decorator


def query(query_type: str) -> Callable[[Callable], Callable]:
    """Decorator: register a method as a query handler.

    Args:
        query_type: The query type name (e.g., "robot_position").
    """
    def decorator(method: Callable) -> Callable:
        setattr(method, "_rois_query_type", query_type)
        return method
    return decorator


def invoke(command_type: str) -> Callable[[Callable], Callable]:
    """Decorator: register a method as an invoke (command) handler.

    Args:
        command_type: The command type name (e.g., "execute", "stop").
            Values are lowercase per the RoIS spec CommandType enum:
            start, stop, suspend, resume, set_parameter, execute.
    """
    def decorator(method: Callable) -> Callable:
        setattr(method, "_rois_command_type", command_type)
        return method
    return decorator


def subscribe(event_type: str) -> Callable[[Callable], Callable]:
    """Decorator: register a method as a subscribe (event) handler.

    Args:
        event_type: The event type name (e.g., "object_detected").
    """
    def decorator(method: Callable) -> Callable:
        setattr(method, "_rois_event_type", event_type)
        return method
    return decorator