"""OpenRoIS component SDK: write a RoIS HRI Component as a Python class.

A component subclasses Component, declares its type with ``@component(profile)``, and
marks the messages it implements::

    from openrois.components.core import Component, component, invoke, subscribe
    from openrois.interfaces.components import NAVIGATION_PROFILE

    @component(NAVIGATION_PROFILE)
    class Navigation(Component):
        @invoke("start")
        async def start(self) -> None:
            ...

The engine that hosts the component stores its parameters, answers component_status,
tracks its commands and serves the part of the profile it implements. A connection that
several components share is a Resource, which the engine opens and closes for them.
"""

from openrois.components.core.component import CommandFailed, Component, EngineBinding
from openrois.components.core.decorators import (
    component,
    invoke,
    on_set_parameter,
    query,
    subscribe,
)
from openrois.components.core.resource import Resource, ResourceBinding

__all__ = [
    "CommandFailed",
    "Component",
    "EngineBinding",
    "Resource",
    "ResourceBinding",
    "component",
    "invoke",
    "on_set_parameter",
    "query",
    "subscribe",
]
