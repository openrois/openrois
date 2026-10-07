"""WebSocket server that puts an engine on the network, for a gateway.

The WsServer accepts two kinds of connections on one port and tells them apart by the
request path:

- ``/adapter``: a child engine (an adapter or a lower gateway). The server reads its
  profile with ``rois.system.get_profile`` and adds it to the engine as a
  :class:`~openrois.engine.child.ChildEngine`. A child whose profile is refused, for
  example for an engine id already in the tree, is closed with code 1008, at discovery
  or when its profile changes.
- Any other path: a client (a service application). The server opens a session for it
  and answers its JSON-RPC requests through the engine.

Each request runs in its own task, so a slow request does not hold up the others on
the same connection. Replies go out as they finish, matched to their requests by id, as
JSON-RPC 2.0 allows. Every message of a connection goes through one
:class:`~openrois.engine.jsonrpc.Outbox`, which keeps a reply ahead of the
notifications it causes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from functools import partial
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.frames import CloseCode

from openrois.engine.child import ChildEngine
from openrois.engine.engine import Engine
from openrois.engine.jsonrpc import Outbox, send_text, serve_session

logger = logging.getLogger(__name__)

#: The request path child engines connect on.
ADAPTER_PATH = "/adapter"

# RFC 6455 limits a close frame's payload to 125 bytes, two of them for the code.
_MAX_CLOSE_REASON_BYTES = 123


class WsServer:
    """WebSocket server for the clients and the child engines of an engine."""

    def __init__(self, engine: Engine, *, child_timeout: float = 10.0) -> None:
        """Initialize the WsServer.

        Args:
            engine: The engine that answers the requests and holds the child engines.
            child_timeout: Seconds to wait for a child engine's reply to a request,
                including the discovery of its profile, before giving up.
        """
        self._engine = engine
        self._child_timeout = child_timeout
        self._server: Server | None = None

    @property
    def port(self) -> int:
        """The bound TCP port, also when the server was started on port 0.

        Raises:
            RuntimeError: If the server is not running.
        """
        if self._server is None:
            raise RuntimeError("The server is not running.")
        port: int = self._server.sockets[0].getsockname()[1]
        return port

    async def start(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        """Start listening. Returns once the server accepts connections.

        Args:
            host: Interface to bind. The default is loopback only, because the server
                does not authenticate its peers.
            port: Port to listen on. Use 0 for an ephemeral port, then read
                :attr:`port`.
        """
        self._server = await serve(self._handle_connection, host, port)
        logger.info("Listening on ws://%s:%d", host, self.port)

    async def stop(self) -> None:
        """Stop the server and close every connection with code 1001.

        Returns once every connection handler has finished, so child engines are
        removed and the sessions of clients closed by then.
        """
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle_connection(self, connection: ServerConnection) -> None:
        if connection.request is not None and connection.request.path == ADAPTER_PATH:
            await self._handle_child(connection)
        else:
            await self._handle_client(connection)

    # -- Child engines -------------------------------------------------------------------

    async def _handle_child(self, connection: ServerConnection) -> None:
        """Discover and add one child engine, and serve it until it disconnects."""
        async def refuse(reason: str) -> None:
            await connection.close(CloseCode.POLICY_VIOLATION, _close_reason(reason))

        child = ChildEngine(
            partial(send_text, connection),
            request_timeout=self._child_timeout,
            check_engine_ids=self._engine.check_engine_ids,
            on_profile_changed=self._engine.profile_changed,
            on_refused=refuse,
        )
        # The reader runs before discovery: the reply to get_profile arrives on this
        # connection, and nothing else reads it.
        reader = asyncio.create_task(_read_child(connection, child))
        added = False
        try:
            try:
                await child.discover()
                self._engine.add_child(child)
            except ValueError as exc:
                logger.warning("Refused a child engine: %s", exc)
                await refuse(str(exc))
                return
            added = True
            logger.info(
                "Child engine %s connected with %d components",
                child.engine_id,
                len(child.profiles()),
            )
            await reader
        finally:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
            child.detach()
            if added:
                self._engine.remove_child(child)
                logger.info("Child engine %s disconnected", child.engine_id)

    # -- Clients -------------------------------------------------------------------------

    async def _handle_client(self, connection: ServerConnection) -> None:
        """Serve one client until it disconnects, then close its session."""
        outbox = Outbox(partial(send_text, connection))
        session = self._engine.open_session(outbox.notify)
        await serve_session(self._engine, session, outbox, connection)


async def _read_child(connection: ServerConnection, child: ChildEngine) -> None:
    """Pass every message from a child engine to its proxy, in order."""
    try:
        async for raw in connection:
            message = _decode(raw)
            if message is None:
                logger.warning("Child engine %s sent a message that is not a JSON object.",
                               child.engine_id)
                continue
            try:
                child.handle(message)
            except Exception:
                logger.exception("Could not handle a message from child engine %s",
                                 child.engine_id)
    except ConnectionClosed:
        pass
    finally:
        # Fail what still waits on the child, discovery included.
        child.detach()


def _close_reason(reason: str) -> str:
    """Shorten a close reason to what fits in a close frame."""
    encoded = reason.encode()
    if len(encoded) <= _MAX_CLOSE_REASON_BYTES:
        return reason
    return encoded[: _MAX_CLOSE_REASON_BYTES - 3].decode(errors="ignore") + "..."


def _decode(raw: str | bytes) -> dict[str, Any] | None:
    """Parse a message from a child engine, or None if it is not a JSON object."""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None
    return payload if isinstance(payload, dict) else None
