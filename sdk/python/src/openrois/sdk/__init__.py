"""OpenRoIS Python client SDK: connect to an OpenRoIS engine over WebSocket.

A client discovers the components of every connected physical robot, virtual avatar, or AI
service, and drives them through the standard RoIS interfaces. Asyncio only.

Public API:
    RoISClient: A connection to an engine, with one method per RoIS operation.
    EngineProfile: What ``RoISClient.get_profile`` returns.
    RoISError: A RoIS operation returned a code other than OK.
    TransportError: The base of the errors below the RoIS operations.
    RoISConnectionError: The WebSocket cannot be opened, or closed.
    RequestTimeoutError: No reply in time.
    RpcError: A protocol fault from the engine.

The condition builders of openrois-interfaces come from here too, so a client needs no second
import to write conditions. ``openrois.sdk.transport`` holds ``WebSocketTransport``, the layer
under the client, for JSON-RPC methods outside the catalog.
"""

from __future__ import annotations

from openrois.interfaces.condition import (
    COMPONENT_REF,
    COMPONENT_TYPE,
    all_of,
    component_ref,
    component_type,
    component_type_urn,
    eq,
    like,
    quote,
)

from openrois.sdk.client import EngineProfile, RoISClient
from openrois.sdk.errors import (
    RequestTimeoutError,
    RoISConnectionError,
    RoISError,
    RpcError,
    TransportError,
)

__all__ = [
    "COMPONENT_REF",
    "COMPONENT_TYPE",
    "EngineProfile",
    "RequestTimeoutError",
    "RoISClient",
    "RoISConnectionError",
    "RoISError",
    "RpcError",
    "TransportError",
    "all_of",
    "component_ref",
    "component_type",
    "component_type_urn",
    "eq",
    "like",
    "quote",
]
