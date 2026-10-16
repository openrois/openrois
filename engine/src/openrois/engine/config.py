"""Configuration of an adapter or a gateway, from defaults, a YAML file, the environment and flags.

Each source overrides the one before it:

1. The defaults of the pydantic model.
2. A YAML file, named by ``--config`` or ``<PREFIX>CONFIG``.
3. ``<PREFIX><NAME>`` environment variables, for the settings the caller names.
4. Command-line flags, for the same settings.

:func:`load_config` is the loader. The gateway uses it with ``OPENROIS_GATEWAY_``, and
every adapter uses it through :func:`load_adapter_config` with ``OPENROIS_ADAPTER_``.

An adapter declares its settings as a subclass of :class:`AdapterConfig`, with one
section per component::

    class SpeechSettings(BaseModel):
        voice: str = "default"

    class MyConfig(AdapterConfig):
        engine_id: str = "my_robot"
        speech: SpeechSettings = SpeechSettings()

    config = load_adapter_config(MyConfig)

Its ``adapter.yaml`` holds the four common settings and the sections::

    gateway_url: ws://127.0.0.1:8765
    engine_id: my_robot
    robot_address: 192.168.1.20
    log_level: info
    speech:
      voice: calm

The environment and the flags set only the four common settings. Everything a component
needs comes from the file.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

type LogLevel = Literal["debug", "info", "warning", "error"]

#: The log levels a flag accepts, lower case.
LOG_LEVELS = ("debug", "info", "warning", "error")

#: Prefix of every environment variable an adapter reads.
ADAPTER_ENV_PREFIX = "OPENROIS_ADAPTER_"


class ConfigError(Exception):
    """Raised when the configuration cannot be read or does not validate."""


def load_config[M: BaseModel](
    model: type[M],
    *,
    env_prefix: str,
    names: Collection[str],
    environ: Mapping[str, str],
    config_file: Path | None = None,
    flags: Mapping[str, object] | None = None,
) -> M:
    """Combine the defaults, the YAML file, the environment and the flags into a model.

    Args:
        model: The pydantic model of the settings.
        env_prefix: Prefix of the environment variables, such as ``OPENROIS_GATEWAY_``.
            ``<prefix>CONFIG`` names the file when ``config_file`` is None.
        names: The top-level settings the environment and the flags may set.
        environ: The environment, usually ``os.environ``.
        config_file: The YAML file, from a flag. It wins over ``<prefix>CONFIG``.
        flags: Values from the command line by setting name. None means the flag was
            not given.

    Raises:
        ConfigError: If the file cannot be read or the result does not validate.
    """
    values: dict[str, Any] = {}

    env_config = environ.get(f"{env_prefix}CONFIG")
    if config_file is None and env_config:
        config_file = Path(env_config)
    if config_file is not None:
        values.update(_read_file(config_file))

    for name in names:
        env_value = environ.get(f"{env_prefix}{name.upper()}")
        if env_value is not None:
            values[name] = env_value

    for name, flag_value in (flags or {}).items():
        if flag_value is not None:
            values[name] = flag_value

    try:
        return model.model_validate(values)
    except ValidationError as exc:
        raise ConfigError(_describe(exc)) from exc


class AdapterConfig(BaseModel):
    """The settings every adapter has. Subclass it with one section per component.

    A subclass gives ``engine_id`` a default by declaring it again, for example
    ``engine_id: str = "my_robot"``. Without one, the engine id must be set.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    gateway_url: str = Field(
        default="ws://127.0.0.1:8765",
        min_length=1,
        description="WebSocket URL of the gateway the adapter connects to.",
    )
    engine_id: str = Field(
        description="Engine id of the adapter, the first part of every component ref.",
    )
    robot_address: str | None = Field(
        default=None,
        description="Where the adapter reaches its robot, if the adapter needs one.",
    )
    log_level: LogLevel = Field(default="info", description="Logging threshold.")

    @field_validator("engine_id")
    @classmethod
    def _engine_id_is_a_ref_part(cls, value: str) -> str:
        return check_engine_id(value)

    @field_validator("log_level", mode="before")
    @classmethod
    def _lower_case_log_level(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value


#: The settings of AdapterConfig that the environment and the flags may set.
ADAPTER_SETTINGS = ("gateway_url", "engine_id", "robot_address", "log_level")


def check_engine_id(value: str) -> str:
    """Refuse an engine id that cannot be the first part of a component ref.

    Raises:
        ValueError: The id is empty or contains a slash.
    """
    if not value:
        raise ValueError("must not be empty")
    # Component refs are engine_id/ref, so a slash would make them ambiguous.
    if "/" in value:
        raise ValueError("must not contain a slash")
    return value


def build_adapter_parser(description: str | None = None) -> argparse.ArgumentParser:
    """The command-line parser of an adapter: ``--config`` and the four common settings.

    Every option defaults to None, so an absent flag leaves the value from the
    environment, the file or the defaults in place.
    """
    prefix = ADAPTER_ENV_PREFIX
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", type=Path, help=f"the adapter.yaml file ({prefix}CONFIG)")
    parser.add_argument("--gateway-url", help=f"the gateway to connect to ({prefix}GATEWAY_URL)")
    parser.add_argument(
        "--engine-id", help=f"the engine id, the first part of every ref ({prefix}ENGINE_ID)"
    )
    parser.add_argument(
        "--robot-address", help=f"where the adapter reaches its robot ({prefix}ROBOT_ADDRESS)"
    )
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVELS,
        type=str.lower,
        help=f"logging threshold ({prefix}LOG_LEVEL, default info)",
    )
    return parser


def load_adapter_config[C: AdapterConfig](
    model: type[C],
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    description: str | None = None,
) -> C:
    """Parse the flags and load the settings of an adapter.

    Args:
        model: The adapter's subclass of AdapterConfig.
        argv: The flags, ``sys.argv[1:]`` when None.
        environ: The environment, ``os.environ`` when None.
        description: What ``--help`` says the adapter is.

    Raises:
        ConfigError: If the file cannot be read or the result does not validate.
        SystemExit: For an unknown flag or ``--help``, as argparse does.
    """
    args = build_adapter_parser(description).parse_args(None if argv is None else list(argv))
    return load_config(
        model,
        env_prefix=ADAPTER_ENV_PREFIX,
        names=ADAPTER_SETTINGS,
        environ=os.environ if environ is None else environ,
        config_file=args.config,
        flags={name: getattr(args, name) for name in ADAPTER_SETTINGS},
    )


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
