"""OpenRoIS core: recursive Engine, WebSocket server and client.

This package provides the recursive Engine class that serves both the
gateway (main engine with child engines) and the adapter (sub-engine with
local components). Both registries can be populated simultaneously.

Public API:
    Engine: The recursive HRI engine.
    WsServer: WebSocket server for the gateway.
    WsClient: WebSocket client for the adapter.
    read_profile: Read a profile YAML file.
    component_config: Build a per-component config dict from a profile.
"""

from __future__ import annotations

from openrois_core.config import component_config, read_profile
from openrois_core.engine import ComponentRegistry, Engine, EventEmitter, SubEngine
from openrois_core.ws_client import WsClient
from openrois_core.ws_server import WsServer

__all__ = [
    "Engine",
    "ComponentRegistry",
    "SubEngine",
    "EventEmitter",
    "WsServer",
    "WsClient",
    "read_profile",
    "component_config",
]