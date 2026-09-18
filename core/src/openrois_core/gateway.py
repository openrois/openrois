"""The OpenRoIS gateway process.

Composes an Engine (the main HRI Engine, enforcing reservations) with a
WsServer, and serves until interrupted. Run it with ``openrois-gateway`` or
``python -m openrois_core.gateway``.

Options come from, in order of precedence, the command line, ``OPENROIS_*``
environment variables, a YAML configuration file (``--config`` or
``OPENROIS_GATEWAY_CONFIG``), and the built-in defaults::

    host: 0.0.0.0
    port: 8765
    engine_id: gateway
    platform: kachaka
    log_level: INFO
    auth:
      key: /run/secrets/jwt-public.pem   # or a shared secret
      algorithm: RS256
      issuer: my-issuer
      audience: openrois
    tls:
      cert: /etc/openrois/cert.pem
      key: /etc/openrois/key.pem

A running gateway answers ``GET /health`` on its port with a JSON summary.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import ssl
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from openrois_core.auth import AuthConfig
from openrois_core.engine import Engine
from openrois_core.ws_server import WsServer

logger = logging.getLogger("openrois.gateway")

# Option name -> (environment variable, built-in default). The configuration file
# uses the option names, with auth.* and tls.* nested under their own keys.
OPTIONS: dict[str, tuple[str, Any]] = {
    "host": ("OPENROIS_HOST", "0.0.0.0"),
    "port": ("OPENROIS_PORT", 8765),
    "engine_id": ("OPENROIS_ENGINE_ID", "gateway"),
    "platform": ("OPENROIS_PLATFORM", ""),
    "log_level": ("OPENROIS_LOG_LEVEL", "INFO"),
    "auth_key": ("OPENROIS_AUTH_KEY", None),
    "auth_algorithm": ("OPENROIS_AUTH_ALGORITHM", "HS256"),
    "auth_issuer": ("OPENROIS_AUTH_ISSUER", None),
    "auth_audience": ("OPENROIS_AUTH_AUDIENCE", None),
    "tls_cert": ("OPENROIS_TLS_CERT", None),
    "tls_key": ("OPENROIS_TLS_KEY", None),
}
CONFIG_ENV = "OPENROIS_GATEWAY_CONFIG"


class ConfigError(ValueError):
    """The configuration file is not usable."""


def load_config(path: str | Path) -> dict[str, Any]:
    """Read a gateway configuration file into flat option names.

    ``auth`` and ``tls`` mappings are flattened to ``auth_key``, ``tls_cert`` and
    so on. Unknown keys are an error, so a typo never silently leaves an option
    at its default.
    """
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    flat: dict[str, Any] = {}
    for key, value in raw.items():
        if key in ("auth", "tls"):
            if not isinstance(value, dict):
                raise ConfigError(f"{path}: {key} must be a mapping")
            for sub, sub_value in value.items():
                flat[f"{key}_{sub}"] = sub_value
        else:
            flat[str(key)] = value
    unknown = sorted(set(flat) - set(OPTIONS))
    if unknown:
        raise ConfigError(f"{path}: unknown option(s): {', '.join(unknown)}")
    if "port" in flat:
        flat["port"] = int(flat["port"])
    return flat


def defaults_from(config: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve each option: environment variable, then the file, then the default."""
    resolved: dict[str, Any] = {}
    for name, (env, default) in OPTIONS.items():
        if env in os.environ:
            value: Any = os.environ[env]
        elif config and name in config:
            value = config[name]
        else:
            value = default
        resolved[name] = int(value) if name == "port" else value
    return resolved


def build_parser(config: dict[str, Any] | None = None) -> argparse.ArgumentParser:
    """The command-line parser, with defaults resolved from the environment and ``config``."""
    d = defaults_from(config)
    parser = argparse.ArgumentParser(
        prog="openrois-gateway",
        description="Run an OpenRoIS gateway (main HRI Engine) on a WebSocket port.",
        epilog="Precedence: command line, OPENROIS_* environment, --config file, defaults. "
        "GET /health on the port answers a JSON liveness summary.",
    )
    parser.add_argument(
        "--config", default=os.environ.get(CONFIG_ENV),
        help=f"YAML configuration file; env {CONFIG_ENV}",
    )
    parser.add_argument("--host", default=d["host"], help="interface to bind (default: all)")
    parser.add_argument("--port", type=int, default=d["port"], help="port (default: 8765)")
    parser.add_argument("--engine-id", default=d["engine_id"], help="engine identifier")
    parser.add_argument("--platform", default=d["platform"], help="platform identifier")
    parser.add_argument(
        "--log-level", default=d["log_level"], choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    auth = parser.add_argument_group("authentication (off unless a key is given)")
    auth.add_argument(
        "--auth-key", default=d["auth_key"],
        help="shared secret (HS256) or public key PEM file (RS256, ES256); env OPENROIS_AUTH_KEY",
    )
    auth.add_argument("--auth-algorithm", default=d["auth_algorithm"], help="JWT algorithm")
    auth.add_argument("--auth-issuer", default=d["auth_issuer"])
    auth.add_argument("--auth-audience", default=d["auth_audience"])
    tls = parser.add_argument_group("TLS (wss:// when both are given)")
    tls.add_argument("--tls-cert", default=d["tls_cert"], help="certificate chain PEM")
    tls.add_argument("--tls-key", default=d["tls_key"], help="private key PEM")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line, reading ``--config`` first so the file supplies defaults."""
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=os.environ.get(CONFIG_ENV))
    known, _ = pre.parse_known_args(argv)
    config = load_config(known.config) if known.config else None
    return build_parser(config).parse_args(argv)


def auth_from_args(args: argparse.Namespace) -> AuthConfig | None:
    """Build the token verifier from the options, reading a PEM file when given."""
    if not args.auth_key:
        return None
    key = args.auth_key
    if os.path.isfile(key):
        with open(key) as f:
            key = f.read()
    return AuthConfig(
        key=key,
        algorithms=(args.auth_algorithm,),
        issuer=args.auth_issuer,
        audience=args.auth_audience,
    )


def ssl_from_args(args: argparse.Namespace) -> ssl.SSLContext | None:
    if not (args.tls_cert and args.tls_key):
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.tls_cert, args.tls_key)
    return context


async def serve(
    host: str,
    port: int,
    engine_id: str = "gateway",
    platform: str = "",
    stop: asyncio.Event | None = None,
    auth: AuthConfig | None = None,
    ssl_context: ssl.SSLContext | None = None,
) -> None:
    """Serve until ``stop`` is set (or forever), then shut the server down cleanly."""
    engine = Engine(engine_id=engine_id, platform=platform, enforce_bindings=True)
    server = WsServer(engine, auth=auth, ssl_context=ssl_context)
    if auth is None:
        logger.warning("Authentication is off: every client on the network can command every robot")
    if ssl_context is None and host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(
            "TLS is off and the gateway listens on %s: tokens and commands travel in "
            "plaintext beyond this host. Pass --tls-cert and --tls-key, or bind 127.0.0.1", host,
        )
    await server.start(host, port)
    stop = stop or asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            # Signal handlers are unavailable on some platforms and in threads.
            pass
    try:
        await stop.wait()
    finally:
        logger.info("Gateway shutting down")
        await server.stop()


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except (ConfigError, OSError) as exc:
        print(f"openrois-gateway: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(serve(
            args.host, args.port, args.engine_id, args.platform,
            auth=auth_from_args(args), ssl_context=ssl_from_args(args),
        ))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
