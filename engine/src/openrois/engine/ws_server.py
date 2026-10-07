"""WebSocket server for an OpenRoIS gateway.

The WsServer accepts two kinds of connections on one port and tells them apart
by the request path:

- ``/adapter``: a child engine (an adapter or a lower gateway). The server
  discovers its components with ``rois.command.search``, registers it with the
  engine, and relays its event notifications to the clients that subscribed.
- Any other path: a client (a service application). The server answers its
  JSON-RPC requests through the engine.

Each request runs in its own task, so a slow command does not hold up the
other requests on the same connection. Replies go out as they finish, matched
to their requests by id, as JSON-RPC 2.0 allows.

Protocol faults that do not depend on the method catalog are answered here:
PARSE_ERROR for a message that is not JSON, INVALID_REQUEST for one that is not
a JSON-RPC request, INVALID_PARAMS for positional params, and INTERNAL_ERROR
when the engine fails. A message without an id is a notification and gets no
reply. METHOD_NOT_FOUND and the validation of params against the catalog are
planned for the engine's move to the method catalog.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from openrois.interfaces.catalog import JsonRpcErrorCode
from openrois.interfaces.hri import ReturnCode
from websockets.asyncio.server import Server, ServerConnection, broadcast, serve
from websockets.exceptions import ConnectionClosed
from websockets.frames import CloseCode

from openrois.engine.engine import ChildEngineProxy, Engine

logger = logging.getLogger(__name__)

#: The request path child engines connect on.
ADAPTER_PATH = "/adapter"

_JSONRPC_VERSION = "2.0"

# RFC 6455 limits a close frame's payload to 125 bytes, two of them for the code.
_MAX_CLOSE_REASON_BYTES = 123


@dataclass
class _Client:
    """A connected service application."""

    connection: ServerConnection
    client_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Subscriptions this client holds, released when it disconnects.
    subscriptions: set[str] = field(default_factory=set)

    async def send_event(self, envelope: dict[str, Any]) -> None:
        """Deliver an event notification relayed from a child engine."""
        message = {"jsonrpc": _JSONRPC_VERSION, "method": "rois.event.notify", "params": envelope}
        await _send(self.connection, message)


class WsServer:
    """WebSocket server that puts an Engine on the network.

    Child engines and clients connect to the same port. The server routes them
    by request path, as described in the module docstring.
    """

    def __init__(self, engine: Engine, *, child_timeout: float = 10.0) -> None:
        """Initialize the WsServer.

        Args:
            engine: The Engine instance to dispatch requests to.
            child_timeout: Seconds to wait for a child engine's reply to a
                forwarded request, including discovery, before giving up.
        """
        self._engine = engine
        self._child_timeout = child_timeout
        self._server: Server | None = None
        self._clients: dict[ServerConnection, _Client] = {}
        self._children: dict[ServerConnection, ChildEngineProxy] = {}

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
            host: Interface to bind. The default is loopback only, because the
                server does not authenticate its peers.
            port: Port to listen on. Use 0 for an ephemeral port, then read
                :attr:`port`.
        """
        self._server = await serve(self._handle_connection, host, port)
        logger.info("Listening on ws://%s:%d", host, self.port)

    async def stop(self) -> None:
        """Stop the server and close every connection with code 1001.

        Returns once every connection handler has finished, so child engines
        are unregistered and client bindings released by then.
        """
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    # -- Connection routing --

    async def _handle_connection(self, connection: ServerConnection) -> None:
        if connection.request is not None and connection.request.path == ADAPTER_PATH:
            await self._handle_child(connection)
        else:
            await self._handle_client(connection)

    # -- Child engines --

    async def _handle_child(self, connection: ServerConnection) -> None:
        """Discover, register and serve one child engine until it disconnects."""
        proxy = ChildEngineProxy(
            connection.send,
            asyncio.get_running_loop(),
            request_timeout=self._child_timeout,
        )
        # The reader must run before discovery: the reply to rois.command.search
        # arrives on this connection, and nothing else reads it.
        reader = asyncio.create_task(self._read_child(connection, proxy))
        registered = False
        try:
            reason = await self._register_child(proxy)
            if reason is not None:
                logger.warning("Refused child engine: %s", reason)
                await connection.close(CloseCode.POLICY_VIOLATION, _close_reason(reason))
                return
            registered = True
            self._children[connection] = proxy
            self._notify_profile_changed()
            logger.info(
                "Child engine %s connected with %d components",
                proxy.engine_id,
                len(proxy.components),
            )
            await reader
        finally:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
            proxy.detach_websocket()
            self._children.pop(connection, None)
            if registered:
                self._engine.unregister_sub_engine(proxy)
                self._notify_profile_changed()
                logger.info("Child engine %s disconnected", proxy.engine_id)

    async def _register_child(self, proxy: ChildEngineProxy) -> str | None:
        """Discover a child engine and register it.

        Returns:
            None on success, or the reason the child engine was refused.
        """
        result = await proxy.discover()
        return_code = result.get("return_code")
        if return_code != ReturnCode.OK.value:
            return f"Discovery failed with {return_code}."
        try:
            self._engine.register_sub_engine(
                proxy.engine_id,
                proxy.components,
                proxy,
                proxy.platform,
            )
        except ValueError as exc:
            return str(exc)
        return None

    async def _read_child(self, connection: ServerConnection, proxy: ChildEngineProxy) -> None:
        """Route replies and notifications from a child engine."""
        try:
            async for raw in connection:
                message = _decode(raw)
                if message is None:
                    logger.warning("Child engine sent a message that is not a JSON object.")
                    continue
                if "id" in message and "method" not in message:
                    proxy.handle_response(message)
                elif "method" in message and "id" not in message:
                    if message["method"] == "rois.event.notify":
                        await proxy.handle_notification(message)
        except ConnectionClosed:
            pass
        finally:
            # Fail any request still waiting for this child, discovery included.
            proxy.detach_websocket()

    # -- Clients --

    async def _handle_client(self, connection: ServerConnection) -> None:
        """Serve one client until it disconnects."""
        client = _Client(connection)
        self._clients[connection] = client
        tasks: set[asyncio.Task[None]] = set()
        try:
            async for raw in connection:
                task = asyncio.create_task(self._handle_message(client, raw))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        except ConnectionClosed:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            del self._clients[connection]
            await self._release_client(client)

    async def _release_client(self, client: _Client) -> None:
        """Drop what a disconnected client held: its bindings and subscriptions."""
        self._engine.release_all(client.client_id)
        for subscribe_id in sorted(client.subscriptions):
            try:
                await self._engine.dispatch(
                    "rois.event.unsubscribe",
                    {"subscribe_id": subscribe_id},
                    None,
                    client.client_id,
                )
            except Exception:
                logger.exception("Could not release subscription %s", subscribe_id)

    async def _handle_message(self, client: _Client, raw: str | bytes) -> None:
        """Answer one message from a client."""
        reply = await self._answer(client, raw)
        if reply is not None:
            await _send(client.connection, reply)

    async def _answer(self, client: _Client, raw: str | bytes) -> dict[str, Any] | None:
        """Build the reply to one message, or None for a notification."""
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _error(None, JsonRpcErrorCode.PARSE_ERROR, "Parse error: invalid JSON")

        if isinstance(payload, dict) and "method" in payload and "id" not in payload:
            # A notification: JSON-RPC 2.0 forbids a reply.
            return None

        request_id = payload.get("id") if isinstance(payload, dict) else None
        if not _is_request(payload):
            return _error(
                request_id if _is_id(request_id) else None,
                JsonRpcErrorCode.INVALID_REQUEST,
                "Invalid Request: not a valid JSON-RPC 2.0 request",
            )

        method: str = payload["method"]
        params = payload.get("params", {})
        if not isinstance(params, dict):
            return _error(
                request_id,
                JsonRpcErrorCode.INVALID_PARAMS,
                "Invalid params: OpenRoIS methods take named params",
            )

        try:
            result = await self._engine.dispatch(
                method, params, client.send_event, client.client_id,
            )
        except Exception:
            logger.exception("Engine failed on %s", method)
            return _error(request_id, JsonRpcErrorCode.INTERNAL_ERROR, "Internal error")

        self._track_subscription(client, method, params, result)
        return {"jsonrpc": _JSONRPC_VERSION, "id": request_id, "result": result}

    @staticmethod
    def _track_subscription(
        client: _Client,
        method: str,
        params: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """Remember the client's subscriptions so a disconnect can release them."""
        if method == "rois.event.subscribe" and result.get("return_code") == ReturnCode.OK.value:
            subscribe_id = result.get("subscribe_id")
            if isinstance(subscribe_id, str) and subscribe_id:
                client.subscriptions.add(subscribe_id)
        elif method == "rois.event.unsubscribe":
            client.subscriptions.discard(str(params.get("subscribe_id", "")))

    def _notify_profile_changed(self) -> None:
        """Tell every client that the engine profile changed."""
        notification = json.dumps({
            "jsonrpc": _JSONRPC_VERSION,
            "method": "rois.system.profile_changed",
            "params": {},
        })
        broadcast(list(self._clients), notification)


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
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_id(value: object) -> bool:
    """Whether a value is a valid JSON-RPC id: a string, a number, or null."""
    return value is None or (isinstance(value, (str, int, float)) and not isinstance(value, bool))


def _is_request(payload: object) -> bool:
    """Whether a payload is a JSON-RPC 2.0 request object with an id."""
    return (
        isinstance(payload, dict)
        and payload.get("jsonrpc") == _JSONRPC_VERSION
        and isinstance(payload.get("method"), str)
        and "id" in payload
        and _is_id(payload["id"])
    )


def _error(request_id: Any, code: JsonRpcErrorCode, message: str) -> dict[str, Any]:
    """Build a JSON-RPC error response."""
    return {
        "jsonrpc": _JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": int(code), "message": message},
    }


async def _send(connection: ServerConnection, message: dict[str, Any]) -> None:
    """Send a message, ignoring a peer that has already gone."""
    try:
        await connection.send(json.dumps(message))
    except ConnectionClosed:
        logger.debug("Dropped a message for a closed connection.")
