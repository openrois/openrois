"""OpenRoIS gateway: the process that hosts the main RoIS HRI Engine.

The gateway composes the engine's ``Engine`` and ``WsServer`` into a process
with configuration from defaults, a YAML file, the environment and flags,
logging, and a graceful stop on SIGTERM and SIGINT.

Public API:
    Gateway: The gateway, to run inside another program or in tests.
    GatewayConfig: Its settings.
    ConfigError: Raised for a configuration that cannot be loaded.
    load_config, parse_config: Build a GatewayConfig from flags and the environment.
    main: The ``openrois-gateway`` command.
"""

from __future__ import annotations

from openrois.gateway.app import Gateway
from openrois.gateway.cli import main
from openrois.gateway.config import ConfigError, GatewayConfig, load_config, parse_config

__all__ = [
    "ConfigError",
    "Gateway",
    "GatewayConfig",
    "load_config",
    "main",
    "parse_config",
]
