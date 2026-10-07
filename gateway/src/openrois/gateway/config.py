"""Gateway configuration from defaults, a YAML file, the environment and flags.

Each source overrides the one before it:

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
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

type LogLevel = Literal["debug", "info", "warning", "error"]

#: Prefix of every environment variable the gateway reads.
ENV_PREFIX = "OPENROIS_GATEWAY_"

#: The environment variable that names the YAML file.
ENV_CONFIG = f"{ENV_PREFIX}CONFIG"


class ConfigError(Exception):
    """Raised when the configuration cannot be read or does not validate."""


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
    def _engine_id_has_no_slash(cls, value: str) -> str:
        # Component refs are engine_id/ref, so a slash would make them ambiguous.
        if "/" in value:
            raise ValueError("must not contain a slash")
        return value

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
        choices=["debug", "info", "warning", "error"],
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
    values: dict[str, Any] = {}

    config_path: Path | None = args.config
    if config_path is None and environ.get(ENV_CONFIG):
        config_path = Path(environ[ENV_CONFIG])
    if config_path is not None:
        values.update(_read_file(config_path))

    names = tuple(GatewayConfig.model_fields)
    for name in names:
        env_value = environ.get(f"{ENV_PREFIX}{name.upper()}")
        if env_value is not None:
            values[name] = env_value

    for name in names:
        flag_value = getattr(args, name)
        if flag_value is not None:
            values[name] = flag_value

    try:
        return GatewayConfig.model_validate(values)
    except ValidationError as exc:
        raise ConfigError(_describe(exc)) from exc


def parse_config(argv: Sequence[str], environ: Mapping[str, str]) -> GatewayConfig:
    """Parse flags and load the configuration in one call."""
    return load_config(build_parser().parse_args(list(argv)), environ)


def _read_file(path: Path) -> dict[str, Any]:
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc.strerror}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if content is None:
        return {}
    if not isinstance(content, dict):
        raise ConfigError(f"{path} must hold a mapping of settings.")
    return {str(key): value for key, value in content.items()}


def _describe(exc: ValidationError) -> str:
    """One line per invalid setting, named as in the YAML file."""
    lines = []
    for error in exc.errors():
        name = ".".join(str(part) for part in error["loc"]) or "config"
        lines.append(f"{name}: {error['msg']}")
    return "Invalid configuration:\n  " + "\n  ".join(lines)
