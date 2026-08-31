"""OpenRoIS component framework: decorators, metadata, result builders.

This package provides the building blocks for creating OpenRoIS components:

- Decorators (@component, @query, @invoke, @subscribe) for declaring
  component handlers.
- ComponentMeta and meta_from_decorators for extracting metadata from
  decorated classes.
- Result builders (results module) for constructing spec-compliant Result
  lists.
"""

from __future__ import annotations

from openrois_components_core.decorators import (
    ComponentFunction,
    component,
    invoke,
    query,
    subscribe,
)
from openrois_components_core.meta import (
    ComponentMeta,
    meta_from_decorators,
)

__all__ = [
    "ComponentFunction",
    "component",
    "invoke",
    "query",
    "subscribe",
    "ComponentMeta",
    "meta_from_decorators",
    "results",
]