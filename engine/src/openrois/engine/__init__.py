"""OpenRoIS engine: the recursive RoIS HRI Engine, with its WebSocket server and client.

One ``Engine`` class serves an adapter (components in its own process), a gateway
(child engines) and a middle tier (both). It answers the RoIS method catalog and
reaches every component through the component contract.

Public API:
    Engine: The recursive HRI engine.
    Session: A client of an engine, or its parent engine.
    ComponentContract: Where the components of an engine live.
    LocalComponent: The shape of a component the engine hosts in its process.
    LocalComponents: The component contract for the components of this process.
    ChildEngine: The component contract for one child engine.
    WsServer: WebSocket server for a gateway.
    WsClient: WebSocket client for an adapter.
    read_profile: Read a profile YAML file.
    component_config: Build a per-component config dict from a profile.
"""

from __future__ import annotations

from openrois.engine.child import ChildEngine
from openrois.engine.config import component_config, read_profile
from openrois.engine.contract import ComponentContract
from openrois.engine.engine import Engine
from openrois.engine.local import LocalComponent, LocalComponents
from openrois.engine.session import Session
from openrois.engine.ws_client import WsClient
from openrois.engine.ws_server import WsServer

__all__ = [
    "ChildEngine",
    "ComponentContract",
    "Engine",
    "LocalComponent",
    "LocalComponents",
    "Session",
    "WsClient",
    "WsServer",
    "component_config",
    "read_profile",
]
