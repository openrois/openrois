"""The OpenRoIS gateway process.

Composes an Engine (the main HRI Engine, enforcing reservations) with a
WsServer, and serves until interrupted. Run it with ``openrois-gateway`` or
``python -m openrois_core.gateway``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import ssl
from collections.abc import Sequence

from openrois_core.auth import AuthConfig
from openrois_core.engine import Engine
from openrois_core.ws_server import WsServer

logger = logging.getLogger("openrois.gateway")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openrois-gateway",
        description="Run an OpenRoIS gateway (main HRI Engine) on a WebSocket port.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="interface to bind (default: all)")
    parser.add_argument("--port", type=int, default=8765, help="port to listen on (default: 8765)")
    parser.add_argument("--engine-id", default="gateway", help="engine identifier in the profile")
    parser.add_argument("--platform", default="", help="platform identifier in the profile")
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    auth = parser.add_argument_group("authentication (off unless a key is given)")
    auth.add_argument(
        "--auth-key", default=os.environ.get("OPENROIS_AUTH_KEY"),
        help="shared secret (HS256) or public key PEM file (RS256, ES256); env OPENROIS_AUTH_KEY",
    )
    auth.add_argument("--auth-algorithm", default="HS256", help="JWT algorithm (default: HS256)")
    auth.add_argument("--auth-issuer", default=os.environ.get("OPENROIS_AUTH_ISSUER"))
    auth.add_argument("--auth-audience", default=os.environ.get("OPENROIS_AUTH_AUDIENCE"))
    tls = parser.add_argument_group("TLS (wss:// when both are given)")
    tls.add_argument(
        "--tls-cert", default=os.environ.get("OPENROIS_TLS_CERT"), help="certificate chain PEM",
    )
    tls.add_argument(
        "--tls-key", default=os.environ.get("OPENROIS_TLS_KEY"), help="private key PEM",
    )
    return parser


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
    args = build_parser().parse_args(argv)
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
