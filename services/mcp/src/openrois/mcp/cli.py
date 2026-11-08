"""The ``openrois-mcp`` command."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from openrois.mcp.config import ConfigError, build_parser, load_settings
from openrois.mcp.server import build_server

logger = logging.getLogger("openrois.mcp")

#: Exit codes of the command.
EXIT_OK = 0
EXIT_CONFIG = 2


def main(argv: Sequence[str] | None = None) -> int:
    """Serve MCP until the agent closes the connection, and return the exit code."""
    args = build_parser().parse_args(sys.argv[1:] if argv is None else list(argv))
    if args.version:
        try:
            print(version("openrois-mcp"))
        except PackageNotFoundError:
            print("unknown")
        return EXIT_OK
    try:
        settings = load_settings(args)
    except ConfigError as exc:
        print(f"openrois-mcp: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    # stdout carries the MCP messages over stdio, so the log goes to stderr.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info(
        "Serving %s over %s, %s",
        settings.gateway_url,
        settings.transport,
        "actions allowed" if settings.allow_actions else "read-only",
    )
    server = build_server(settings)
    if settings.transport == "stdio":
        server.run("stdio")
    else:
        if settings.host not in ("127.0.0.1", "localhost", "::1"):
            logger.warning(
                "Listening on %s. The server has no authentication, so anyone who reaches "
                "it can drive the components it allows.",
                settings.host,
            )
        server.run("streamable-http", host=settings.host, port=settings.port)
    return EXIT_OK
