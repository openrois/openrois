"""The settings of the MCP server: defaults, then environment variables, then flags."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

Transport = Literal["stdio", "streamable-http"]

#: The prefix of every environment variable the server reads.
ENV_PREFIX = "OPENROIS_MCP_"

#: Whether run_commands binds the components it names when the agent has not. Off, so an
#: agent binds on purpose and sees a busy component as a failed bind. One constant, so the
#: default can change in one place.
AUTO_BIND_DEFAULT = False


class ConfigError(ValueError):
    """A setting has a value the server cannot use."""


@dataclass(frozen=True, slots=True)
class Settings:
    """How the server reaches the gateway and what it lets an agent do.

    Attributes:
        gateway_url: The WebSocket URL of the gateway or engine.
        allow_actions: Offer the tools that bind, set parameters and run commands. Off, the
            server is read-only.
        allow: CQL2 LIKE patterns on component refs, such as ``reachy_real/%``. A component
            can be bound, configured or commanded only if one matches. Empty allows every
            component. Discovery shows every component either way.
        command_timeout: The longest a tool waits for a command to end, in seconds.
        event_buffer: How many notifications the server keeps for get_events.
        idle_release: Release a bind after this many seconds without a call on its
            component. None keeps binds until release, disconnect or shutdown.
        request_timeout: How long one RoIS call waits for its reply, in seconds.
        transport: How the agent reaches the server.
        host: The interface of the streamable-http transport.
        port: The port of the streamable-http transport.
    """

    gateway_url: str = "ws://127.0.0.1:8765"
    allow_actions: bool = False
    allow: tuple[str, ...] = ()
    command_timeout: float = 60.0
    event_buffer: int = 500
    idle_release: float | None = None
    request_timeout: float = 30.0
    transport: Transport = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000


def build_parser() -> argparse.ArgumentParser:
    """The command-line flags. Each has an OPENROIS_MCP_* environment variable."""
    parser = argparse.ArgumentParser(
        prog="openrois-mcp",
        description=(
            "Serve the components behind an OpenRoIS gateway to an AI agent over MCP. "
            "Read-only unless --allow-actions is given."
        ),
    )
    parser.add_argument("--gateway-url", help="WebSocket URL of the gateway")
    parser.add_argument(
        "--allow-actions",
        action="store_true",
        default=None,
        help="offer bind, release, set_parameters and run_commands",
    )
    parser.add_argument(
        "--allow",
        action="append",
        metavar="PATTERN",
        help="CQL2 LIKE pattern of the component refs an agent may act on, repeatable",
    )
    parser.add_argument("--command-timeout", type=float, help="longest wait for a command, s")
    parser.add_argument("--event-buffer", type=int, help="notifications kept for get_events")
    parser.add_argument(
        "--idle-release", type=float, metavar="SECONDS", help="release idle binds after this"
    )
    parser.add_argument("--request-timeout", type=float, help="wait for one RoIS reply, s")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"])
    parser.add_argument("--host", help="interface of the streamable-http transport")
    parser.add_argument("--port", type=int, help="port of the streamable-http transport")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    return parser


def load_settings(args: argparse.Namespace, environ: Mapping[str, str] | None = None) -> Settings:
    """Merge the defaults, the environment and the parsed flags.

    Raises:
        ConfigError: A value is out of range or not a number.
    """
    env = os.environ if environ is None else environ
    defaults = Settings()

    def pick(flag: object, name: str) -> str | None:
        if flag is not None:
            return str(flag)
        return env.get(ENV_PREFIX + name)

    def number(flag: object, name: str, default: float) -> float:
        raw = pick(flag, name)
        if raw is None or raw == "":
            return default
        try:
            value = float(raw)
        except ValueError as exc:
            raise ConfigError(f"{name.lower()} must be a number, not {raw!r}") from exc
        if value <= 0:
            raise ConfigError(f"{name.lower()} must be above zero, not {raw!r}")
        return value

    allow_actions_raw = pick(args.allow_actions, "ALLOW_ACTIONS")
    allow_actions = (allow_actions_raw or "").strip().lower() in ("1", "true", "yes", "on")

    patterns: Sequence[str] = args.allow or [
        part.strip() for part in env.get(ENV_PREFIX + "ALLOW", "").split(",") if part.strip()
    ]

    idle_raw = pick(args.idle_release, "IDLE_RELEASE")
    try:
        idle_seconds = float(idle_raw) if idle_raw else 0.0
    except ValueError as exc:
        raise ConfigError(f"idle_release must be a number, not {idle_raw!r}") from exc
    # Zero or less turns the idle release off, which is the default.
    idle = idle_seconds if idle_seconds > 0 else None

    transport = pick(args.transport, "TRANSPORT") or defaults.transport
    if transport not in ("stdio", "streamable-http"):
        raise ConfigError(f"transport must be stdio or streamable-http, not {transport!r}")

    return Settings(
        gateway_url=pick(args.gateway_url, "GATEWAY_URL") or defaults.gateway_url,
        allow_actions=allow_actions,
        allow=tuple(patterns),
        command_timeout=number(args.command_timeout, "COMMAND_TIMEOUT", defaults.command_timeout),
        event_buffer=int(number(args.event_buffer, "EVENT_BUFFER", defaults.event_buffer)),
        idle_release=idle,
        request_timeout=number(args.request_timeout, "REQUEST_TIMEOUT", defaults.request_timeout),
        transport="stdio" if transport == "stdio" else "streamable-http",
        host=pick(args.host, "HOST") or defaults.host,
        port=int(number(args.port, "PORT", defaults.port)),
    )
