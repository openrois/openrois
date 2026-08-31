"""Component metadata extracted from decorator attributes.

ComponentMeta is a dataclass that captures the metadata set by the
@component, @query, @invoke, and @subscribe decorators. The engine
reads this metadata at registration time to route JSON-RPC requests
to the correct handler methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openrois_components_core.decorators import (
    _ROIS_COMPONENT_REF,
    _ROIS_FUNCTION,
    _ROIS_INVOKES,
    _ROIS_PARAMETERS,
    _ROIS_QUERIES,
    _ROIS_SUBSCRIBES,
    ComponentFunction,
)


@dataclass
class ComponentMeta:
    """Metadata for a registered component handler class.

    Collected from the decorator attributes set by @component, @query,
    @invoke, and @subscribe.

    Attributes:
        ref: The component ref (e.g., "Navigation").
        function: The RoSO function classification (actuation, sensing,
            function, or None). The engine derives binding enforcement
            from this: actuation components with command methods require
            exclusive binding.
        queries: Maps query_type string to method name.
        invokes: Maps command_type string to method name.
        subscribes: Maps event_type string to method name.
        parameters: List of parameter profile dicts.
    """

    ref: str
    function: ComponentFunction | None
    queries: dict[str, str] = field(default_factory=dict)
    invokes: dict[str, str] = field(default_factory=dict)
    subscribes: dict[str, str] = field(default_factory=dict)
    parameters: list[dict[str, Any]] = field(default_factory=list)


def meta_from_decorators(cls: type) -> ComponentMeta:
    """Extract ComponentMeta from a class decorated with @component.

    Reads the decorator metadata attributes set on the class and its
    methods by @component, @query, @invoke, and @subscribe.

    Args:
        cls: The decorated component class.

    Returns:
        A ComponentMeta with the extracted metadata.
    """
    # Collect decorated method names from the class.
    queries: dict[str, str] = {}
    invokes: dict[str, str] = {}
    subscribes: dict[str, str] = {}

    for method_name in dir(cls):
        method = getattr(cls, method_name, None)
        if method is None:
            continue
        if hasattr(method, "_rois_query_type"):
            queries[getattr(method, "_rois_query_type")] = method_name
        if hasattr(method, "_rois_command_type"):
            invokes[getattr(method, "_rois_command_type")] = method_name
        if hasattr(method, "_rois_event_type"):
            subscribes[getattr(method, "_rois_event_type")] = method_name

    # Merge with any dicts already set by the decorator (inherited).
    existing_queries = getattr(cls, _ROIS_QUERIES, {})
    existing_invokes = getattr(cls, _ROIS_INVOKES, {})
    existing_subscribes = getattr(cls, _ROIS_SUBSCRIBES, {})
    queries = {**existing_queries, **queries}
    invokes = {**existing_invokes, **invokes}
    subscribes = {**existing_subscribes, **subscribes}

    return ComponentMeta(
        ref=getattr(cls, _ROIS_COMPONENT_REF, ""),
        function=getattr(cls, _ROIS_FUNCTION, None),
        queries=queries,
        invokes=invokes,
        subscribes=subscribes,
        parameters=getattr(cls, _ROIS_PARAMETERS, []),
    )