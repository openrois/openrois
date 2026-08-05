"""OpenRoIS Adapter SDK: build robot-side adapters for the OpenRoIS middleware.

Public API:
    RobotAdapter: base class for adapters. Subclass and nest @component classes.
    component: decorator to register a class as a component handler.
    query: decorator to register a method as a query handler.
    invoke: decorator to register a method as an invoke (command) handler.
    subscribe: decorator to register a method as a subscribe (event) handler.
    results: helper functions for building common Result lists.
    load_config: load a robot-adapter YAML config file.
"""

from __future__ import annotations

from openrois.sdk import results
from openrois.sdk.adapter import RobotAdapter, component, invoke, query, subscribe
from openrois.sdk.config import load_config

__all__ = [
    "RobotAdapter",
    "component",
    "query",
    "invoke",
    "subscribe",
    "results",
    "load_config",
]
