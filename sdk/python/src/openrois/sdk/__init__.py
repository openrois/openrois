"""OpenRoIS Adapter SDK: build robot-side adapters for the OpenRoIS middleware.

Public API:
    RobotAdapter: base class for adapters. Subclass and nest @component classes.
    AdapterFramework: runtime that connects the adapter to the avatar via WS.
    component: decorator to register a class as a component handler.
    query: decorator to register a method as a query handler.
    invoke: decorator to register a method as an invoke (command) handler.
    subscribe: decorator to register a method as a subscribe (event) handler.
    results: helper functions for building common Result lists.
    load_config: load a robot-adapter YAML config file.
    InvokeResponse: return type of @invoke handlers. Re-exported from
        openrois.interfaces.bus so adapter authors import only from the SDK.
    ReturnCode: enum used in InvokeResponse. Re-exported from
        openrois.interfaces.hri so adapter authors import only from the SDK.
    Result: element of query and event result lists. Re-exported from
        openrois.interfaces.hri so adapter authors import only from the SDK.
"""

from __future__ import annotations

from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import Result, ReturnCode
from openrois.sdk import results
from openrois.sdk.adapter import RobotAdapter, component, invoke, query, subscribe
from openrois.sdk.config import load_config
from openrois.sdk.framework import AdapterFramework

__all__ = [
    "RobotAdapter",
    "AdapterFramework",
    "component",
    "query",
    "invoke",
    "subscribe",
    "results",
    "load_config",
    "InvokeResponse",
    "ReturnCode",
    "Result",
]
