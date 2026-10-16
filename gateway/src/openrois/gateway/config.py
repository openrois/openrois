"""Gateway configuration from defaults, a YAML file, the environment and flags.

The loader is the one adapters use, in openrois.engine.config. Each source overrides the
one before it:

1. The defaults of :class:`GatewayConfig`.
2. A YAML file, named by ``--config`` or ``OPENROIS_GATEWAY_CONFIG``.
3. ``OPENROIS_GATEWAY_*`` environment variables.
4. Command-line flags.

The YAML file is a flat mapping with the field names of :class:`GatewayConfig`::

    host: 0.0.0.0
    port: 8765
    engine_id: gateway
    log_level: info
    child_timeout: 10
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path

from openrois.engine.config import LOG_LEVELS, ConfigError, LogLevel, check_engine_id
from openrois.engine.config import load_config as _load_config
from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "ENV_CONFIG",
    "ENV_PREFIX",
    "ConfigError",
    "GatewayConfig",
    "LogLevel",
    "build_parser",
    "load_config",
    "parse_config",
]

#: Prefix of every environment variable the gateway reads.
ENV_PREFIX = "OPENROIS_GATEWAY_"

#: The environment variable that names the YAML file.
ENV_CONFIG = f"{ENV_PREFIX}CONFIG"


class GatewayConfig(BaseModel):
    """Settings of one gateway process."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(
        default="127.0.0.1",
        min_length=1,
        description=(
            "Interface to bind. Loopback by default, because the gateway does not "
            "authenticate its peers. Use 0.0.0.0 to accept connections from other hosts."
        ),
    )
    port: int = Field(default=8765, ge=0, le=65535, description="TCP port. 0 picks a free port.")
    engine_id: str = Field(
        default="gateway",
        min_length=1,
        description="Engine id of the main HRI Engine, reported in its profile.",
    )
    log_level: LogLevel = Field(default="info", description="Logging threshold.")
    child_timeout: float = Field(
        default=10.0,
        gt=0,
        description="Seconds to wait for a child engine's reply to a forwarded request.",
    )

    @field_validator("engine_id")
    @classmethod
    def _engine_id_is_a_ref_part(cls, value: str) -> str:
        return check_engine_id(value)

    @field_validator("log_level", mode="before")
    @classmethod
    def _lower_case_log_level(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser of ``openrois-gateway``.

    Every option defaults to None, so an absent flag leaves the value from the
    environment, the file or the defaults in place.
    """
    parser = argparse.ArgumentParser(
        prog="openrois-gateway",
        description="Run an OpenRoIS gateway: the main RoIS HRI Engine on a WebSocket port.",
    )
    parser.add_argument("--config", type=Path, help=f"YAML file with settings ({ENV_CONFIG})")
    parser.add_argument("--host", help=f"interface to bind ({ENV_PREFIX}HOST, default 127.0.0.1)")
    parser.add_argument(
        "--port", type=int, help=f"TCP port, 0 for a free one ({ENV_PREFIX}PORT, default 8765)"
    )
    parser.add_argument(
        "--engine-id", help=f"engine id of the main engine ({ENV_PREFIX}ENGINE_ID, default gateway)"
    )
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVELS,
        type=str.lower,
        help=f"logging threshold ({ENV_PREFIX}LOG_LEVEL, default info)",
    )
    parser.add_argument(
        "--child-timeout",
        type=float,
        help=f"seconds to wait for a child engine ({ENV_PREFIX}CHILD_TIMEOUT, default 10)",
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    return parser


def load_config(
    args: argparse.Namespace,
    environ: Mapping[str, str],
) -> GatewayConfig:
    """Combine the defaults, the YAML file, the environment and the flags.

    Args:
        args: Parsed flags from :func:`build_parser`.
        environ: The environment, usually ``os.environ``.

    Raises:
        ConfigError: If the file cannot be read or the result does not validate.
    """
    names = tuple(GatewayConfig.model_fields)
    return _load_config(
        GatewayConfig,
        env_prefix=ENV_PREFIX,
        names=names,
        environ=environ,
        config_file=args.config,
        flags={name: getattr(args, name) for name in names},
    )


def parse_config(argv: Sequence[str], environ: Mapping[str, str]) -> GatewayConfig:
    """Parse flags and load the configuration in one call."""
    return load_config(build_parser().parse_args(list(argv)), environ)
