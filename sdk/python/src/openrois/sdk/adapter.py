"""Base class and decorators for building OpenRoIS adapters.

The roboticist subclasses RobotAdapter and nests @component classes. Each
component class has @query, @invoke, and @subscribe decorated methods. The
framework (AdapterFramework, in framework.py) reads the decorator metadata
and routes JSON-RPC to the right handler method.

Usage::

    class MyAdapter(RobotAdapter):
        @component("Navigation", bind_required=True)
        class Navigation:
            @query("waypoints")
            async def get_waypoints(self):
                return results.waypoints(self.parent._waypoints)

            @invoke("EXECUTE")
            async def navigate(self, parameters):
                ...

            @subscribe("reached_target")
            async def on_reached(self):
                ...
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Decorator metadata storage
# ---------------------------------------------------------------------------

_ROIS_COMPONENT_REF = "_rois_component_ref"
_ROIS_BIND_REQUIRED = "_rois_bind_required"
_ROIS_QUERIES = "_rois_queries"
_ROIS_INVOKES = "_rois_invokes"
_ROIS_SUBSCRIBES = "_rois_subscribes"


def component(ref: str, *, bind_required: bool = False) -> Callable[[type], type]:
    """Decorator: register a class as a handler for a component ref.

    Args:
        ref: The component ref (e.g., "Navigation").
        bind_required: Whether the operator must bind before execute.
    """
    def decorator(cls: type) -> type:
        setattr(cls, _ROIS_COMPONENT_REF, ref)
        setattr(cls, _ROIS_BIND_REQUIRED, bind_required)
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
        command_type: The command type name (e.g., "EXECUTE", "STOP").
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


# ---------------------------------------------------------------------------
# Component metadata collected at class level
# ---------------------------------------------------------------------------


class ComponentMetadata:
    """Metadata for a registered component handler class.

    Collected by RobotAdapter._init_components() from the decorator attributes.
    """

    def __init__(
        self,
        ref: str,
        bind_required: bool,
        queries: dict[str, str],
        invokes: dict[str, str],
        subscribes: dict[str, str],
    ) -> None:
        self.ref = ref
        self.bind_required = bind_required
        self.queries = queries
        self.invokes = invokes
        self.subscribes = subscribes


# ---------------------------------------------------------------------------
# RobotAdapter base class
# ---------------------------------------------------------------------------


class RobotAdapter:
    """Base class for OpenRoIS adapters.

    Subclass this and nest @component classes. The framework instantiates
    each component class, sets .parent to the adapter instance, and routes
    JSON-RPC methods to the decorated handler methods.

    The roboticist accesses adapter state from component handlers via
    self.parent (e.g., self.parent.nav_client).

    Attributes:
        config: The loaded config dict from the YAML file.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._handlers: dict[str, Any] = {}
        self._metadata: dict[str, ComponentMetadata] = {}
        self._init_components()

    def _init_components(self) -> None:
        """Find all @component-decorated nested classes and instantiate them."""
        for attr_name in dir(self):
            attr = getattr(self, attr_name, None)
            if attr is None:
                continue
            # Check if this is a class with the component ref attribute.
            if isinstance(attr, type) and hasattr(attr, _ROIS_COMPONENT_REF):
                ref = getattr(attr, _ROIS_COMPONENT_REF)
                bind_required = getattr(attr, _ROIS_BIND_REQUIRED, False)
                # Collect decorated method names.
                queries: dict[str, str] = {}
                invokes: dict[str, str] = {}
                subscribes: dict[str, str] = {}
                for method_name in dir(attr):
                    method = getattr(attr, method_name, None)
                    if method is None:
                        continue
                    if hasattr(method, "_rois_query_type"):
                        queries[getattr(method, "_rois_query_type")] = method_name
                    if hasattr(method, "_rois_command_type"):
                        invokes[getattr(method, "_rois_command_type")] = method_name
                    if hasattr(method, "_rois_event_type"):
                        subscribes[getattr(method, "_rois_event_type")] = method_name
                # Instantiate the handler and set parent reference.
                handler = attr()
                handler.parent = self  # type: ignore[attr-defined]
                self._handlers[ref] = handler
                self._metadata[ref] = ComponentMetadata(
                    ref=ref,
                    bind_required=bind_required,
                    queries=queries,
                    invokes=invokes,
                    subscribes=subscribes,
                )

    def get_component_list(self) -> list[dict[str, Any]]:
        """Return the component list for registration with the avatar.

        Each entry has: ref, type, bind_required, queries, commands, events.
        """
        components: list[dict[str, Any]] = []
        for ref, meta in self._metadata.items():
            components.append({
                "ref": ref,
                "type": "user-defined",
                "bind_required": meta.bind_required,
                "queries": list(meta.queries.keys()),
                "commands": list(meta.invokes.keys()),
                "events": list(meta.subscribes.keys()),
            })
        return components

    def get_handler(self, ref: str) -> Any | None:
        """Get the handler instance for a component ref."""
        return self._handlers.get(ref)

    def get_metadata(self, ref: str) -> ComponentMetadata | None:
        """Get the metadata for a component ref."""
        return self._metadata.get(ref)
