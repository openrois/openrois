"""OpenRoIS MCP server: the components behind a gateway as tools for an AI agent.

One server process holds one RoIS session. It is read-only unless started with
``--allow-actions``.

Public API:
    build_server: An MCPServer for a gateway.
    Session: The RoIS session behind the tools.
    Settings: What the server reaches and allows.
"""

from __future__ import annotations

from openrois.mcp.config import Settings
from openrois.mcp.server import build_server
from openrois.mcp.session import Session

__all__ = ["Session", "Settings", "build_server"]
