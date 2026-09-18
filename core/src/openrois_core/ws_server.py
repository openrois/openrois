"""WebSocket server for the OpenRoIS gateway.

The WsServer accepts connections from both adapters (sub-engines) and
clients (operators, avatars). It distinguishes them by URL path:
/adapter connections are child engines discovered through their profile,
all other paths are clients that send RoIS operations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import websockets
from openrois.interfaces.bus import EventEnvelope

from openrois_core.engine import Engine, SubEngine, envelope_to_notification

logger = logging.getLogger(__name__)


def _ws_path(ws: Any) -> str:
    """Return the URL path of a connection.

    websockets 14 and later expose it on connection.request.path, the legacy
    API on ws.path.
    """
    request = getattr(ws, "request", None)
    if request is not None:
        return str(getattr(request, "path", "/"))
    return str(getattr(ws, "path", "/"))


def _ws_is_open(ws: Any) -> bool:
    """Whether a connection is open, on the new and the legacy API."""
    state = getattr(ws, "state", None)
    if state is not None:
        return getattr(state, "name", "") == "OPEN"
    return not getattr(ws, "closed", False)


class WsServer:
    """WebSocket server with role-based routing for the OpenRoIS gateway.

    Adapters and clients connect to the same port. The server distinguishes
    them by the messages they send and routes accordingly.
    """

    def __init__(self, engine: Engine) -> None:
        """Initialize the WsServer.

        Args:
            engine: The Engine instance to dispatch requests to.
        """
        self._engine = engine
        self._server: Any = None
        self._sub_engines: dict[Any, SubEngine] = {}
        # client WebSocket -> subscribe_ids it holds, released when it leaves
        self._client_subscriptions: dict[Any, set[str]] = {}
        # All client WebSockets (for profile-change broadcasts)
        self._client_sockets: set[Any] = set()

    async def start(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
    ) -> None:
        """Start the WebSocket server.

        Args:
            host: Host to bind (default: 0.0.0.0, all interfaces).
            port: Port to listen on (default: 8765).
        """
        self._server = await websockets.serve(
            self._handle_connection,
            host,
            port,
        )
        logger.info("Gateway listening on ws://%s:%d", host, port)

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        for sub_engine in self._sub_engines.values():
            if sub_engine.engine_id:
                self._engine.unregister_sub_engine(sub_engine.engine_id)
        self._sub_engines.clear()

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._client_subscriptions.clear()
        self._client_sockets.clear()

    def _notify_profile_changed(self) -> None:
        """Broadcast a profile_changed notification to all connected clients."""
        notification = json.dumps({
            "jsonrpc": "2.0",
            "method": "rois.system.profile_changed",
            "params": {},
        })
        for ws in list(self._client_sockets):
            if _ws_is_open(ws):
                asyncio.ensure_future(ws.send(notification))

    async def _handle_connection(self, ws: Any) -> None:
        """Handle a new WebSocket connection.

        Routes by URL path: /adapter connections are sub-engines that
        get discovered via rois.command.search. All other paths are
        clients that send RoIS operations.
        """
        path = _ws_path(ws)
        is_adapter = "/adapter" in path

        if is_adapter:
            await self._handle_adapter_connection(ws)
        else:
            await self._handle_client_connection(ws)

    async def _handle_adapter_connection(self, ws: Any) -> None:
        """Handle a child engine (adapter) connection.

        Discovers the adapter through its profile, registers it, broadcasts
        profile_changed, and then serves its responses and event notifications
        until it disconnects.
        """
        loop = asyncio.get_running_loop()

        async def ws_send(data: str) -> None:
            await ws.send(data)

        sub_engine = SubEngine(ws_send, loop)
        # The receive loop must run while discover() awaits its response, or
        # the response is never read and discovery times out.
        receive_task = asyncio.ensure_future(self._adapter_receive_loop(ws, sub_engine))

        try:
            await sub_engine.discover()
            self._sub_engines[ws] = sub_engine
            self._engine.register_sub_engine(
                sub_engine.engine_id,
                sub_engine.components,
                sub_engine,
                sub_engine.platform,
            )
            self._notify_profile_changed()
            logger.info(
                "Adapter %s connected with %d components",
                sub_engine.engine_id,
                len(sub_engine.components),
            )
            await receive_task
        except websockets.ConnectionClosed:
            pass
        finally:
            receive_task.cancel()
            logger.info("Adapter %s disconnected", sub_engine.engine_id)
            if sub_engine.engine_id:
                self._engine.unregister_sub_engine(sub_engine.engine_id)
            sub_engine.detach_websocket()
            self._sub_engines.pop(ws, None)
            self._notify_profile_changed()

    async def _adapter_receive_loop(self, ws: Any, sub_engine: SubEngine) -> None:
        """Route responses to pending requests and notifications to their sinks."""
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from adapter: %s", raw[:100])
                continue
            has_id = "id" in msg
            has_method = "method" in msg
            if has_id and not has_method:
                sub_engine.handle_response(msg)
            elif has_method and not has_id:
                # Events, completions, and errors from the child engine.
                await sub_engine.handle_notification(msg)

    async def _handle_client_connection(self, ws: Any) -> None:
        """Handle a client (service application) connection."""
        client_id = str(uuid.uuid4())
        self._client_sockets.add(ws)
        self._client_subscriptions[ws] = set()

        async def sink(envelope: EventEnvelope) -> None:
            """Push one event to this client as a rois.event.notify notification."""
            if not _ws_is_open(ws):
                return
            await ws.send(json.dumps(envelope_to_notification(envelope)))

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON: %s", raw[:100])
                    continue

                has_id = "id" in msg
                has_method = "method" in msg

                if has_id and has_method:
                    request_id = msg["id"]
                    method = msg["method"]
                    params = msg.get("params", {})
                    try:
                        result = await self._engine.dispatch(method, params, sink, client_id)
                        self._track_subscription(ws, method, params, result)
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": result,
                        }))
                    except Exception as exc:
                        logger.error("Dispatch error: %s", exc)
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {"code": -32603, "message": "Internal error"},
                        }))
                    continue

                # A notification from the client: only unsubscribe is meaningful.
                if has_method and not has_id and msg["method"] == "rois.event.unsubscribe":
                    params = msg.get("params", {})
                    result = await self._engine.dispatch(
                        "rois.event.unsubscribe", params, sink, client_id,
                    )
                    self._track_subscription(ws, "rois.event.unsubscribe", params, result)

        except websockets.ConnectionClosed:
            pass
        finally:
            self._engine.release_all(client_id)
            self._client_sockets.discard(ws)
            # Release the subscriptions this client still holds, upstream too.
            for subscribe_id in self._client_subscriptions.pop(ws, set()):
                try:
                    await self._engine.dispatch(
                        "rois.event.unsubscribe", {"subscribe_id": subscribe_id}, None, client_id,
                    )
                except Exception as exc:
                    logger.warning("Cleanup unsubscribe %s failed: %s", subscribe_id, exc)

    def _track_subscription(
        self,
        ws: Any,
        method: str,
        params: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """Remember which subscriptions a client holds so they can be released."""
        held = self._client_subscriptions.setdefault(ws, set())
        if method == "rois.event.subscribe" and result.get("subscribe_id"):
            held.add(str(result["subscribe_id"]))
        elif method == "rois.event.unsubscribe":
            held.discard(str(params.get("subscribe_id", "")))
