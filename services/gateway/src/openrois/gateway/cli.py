"""The ``openrois-gateway`` command."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from openrois.gateway.app import Gateway
from openrois.gateway.config import ConfigError, LogLevel, build_parser, load_config

logger = logging.getLogger("openrois.gateway")

#: Exit codes of the command.
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFIG = 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run a gateway until SIGTERM or SIGINT, and return the exit code.

    Returns 0 after a graceful stop, 1 when the gateway cannot start (for
    example because the port is taken), and 2 for an invalid configuration.
    """
    args = build_parser().parse_args(sys.argv[1:] if argv is None else list(argv))
    if args.version:
        print(f"openrois-gateway {package_version()}")
        return EXIT_OK

    try:
        config = load_config(args, os.environ)
    except ConfigError as exc:
        print(f"openrois-gateway: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    configure_logging(config.log_level)
    logger.info(
        "Starting OpenRoIS gateway %s, engine id %s", package_version(), config.engine_id
    )
    try:
        asyncio.run(Gateway(config).run())
    except OSError as exc:
        logger.error("Cannot start the gateway: %s", exc)
        return EXIT_FAILURE
    except KeyboardInterrupt:
        # Reached only where signal handlers are unavailable, such as Windows.
        logger.info("Stopped")
    return EXIT_OK


def configure_logging(level: LogLevel) -> None:
    """Log to standard error, one line per record."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def package_version() -> str:
    """The installed version of openrois-gateway."""
    try:
        return version("openrois-gateway")
    except PackageNotFoundError:
        return "unknown"
