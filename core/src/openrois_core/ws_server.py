"""WebSocket server for the OpenRoIS gateway.

The WsServer accepts connections from both adapters (sub-engines) and
clients (operators, avatars). It distinguishes them by the messages they
send:

- rois.adapter.register (has id + method) -> adapter connection, creates
  a SubEngine and registers it with the Engine.
- rois.system.* / rois.command.* / rois.query.* / rois.event.* -> client
  connection, dispatched to the Engine.
- JSON-RPC response (has id, no method) -> from adapter, resolving a
  pending request in the SubEngine.
- JSON-RPC notification (has method, no id) -> from adapter, event push.

Event relay: when an adapter sends rois.event.notify, the WsServer
pushes the notification to all subscribed client WebSockets.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import websockets

from openrois_core.engine import Engine, SubEngine

logger = logging.getLogger(__name__)


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
        self._server: websockets.WebSocketServer | None = None
        self._sub_engines: dict[Any, SubEngine] = {}
        # subscribe_id -> set of client WebSockets to push events to
        self._client_subscriptions: dict[str, set] = {}
        # All client WebSockets (for profile-change broadcasts)
        self._client_sockets: set = set()

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
            if not ws.closed:
                asyncio.ensure_future(ws.send(notification))

    async def _handle_connection(self, ws: Any) -> None:
        """Handle a new WebSocket connection.

        Determines the role (adapter or client) from the first message
        and routes subsequent messages accordingly.
        """
        role: str = "unknown"
        sub_engine: SubEngine | None = None
        client_id: str = ""

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON: %s", raw[:100])
                    continue

                has_id = "id" in msg
                has_method = "method" in msg

                # Adapter registration
                if has_id and has_method and msg["method"] == "rois.adapter.register":
                    role = "adapter"
                    loop = asyncio.get_running_loop()

                    async def ws_send(data: str) -> None:
                        await ws.send(data)

                    sub_engine = SubEngine(ws_send, loop)
                    sub_engine.handle_register(msg)
                    self._sub_engines[ws] = sub_engine
                    self._engine.register_sub_engine(
                        sub_engine.engine_id,
                        sub_engine.components,
                        sub_engine,
                        sub_engine.platform,
                    )
                    # Send registration response
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "id": msg["id"],
                        "result": {"return_code": "OK"},
                    }))
                    self._notify_profile_changed()
                    continue

                # Adapter responses and notifications
                if role == "adapter" and sub_engine:
                    # Response: has id, no method
                    if has_id and not has_method:
                        sub_engine.handle_response(msg)
                        continue
                    # Notification: has method, no id
                    if has_method and not has_id:
                        if msg["method"] == "rois.event.notify":
                            self._relay_event_to_clients(msg.get("params", {}))
                        continue
                    continue

                # Client messages
                if role == "unknown":
                    role = "client"
                    self._client_sockets.add(ws)
                    client_id = str(uuid.uuid4())

                if role == "client" and has_id and has_method:
                    request_id = msg["id"]
                    method = msg["method"]
                    params = msg.get("params", {})

                    # Create an event sink that pushes events to this client.
                    async def sink(envelope: dict) -> None:
                        subscribe_id = envelope.get("subscribe_id", "")
                        notification = json.dumps({
                            "jsonrpc": "2.0",
                            "method": "rois.event.notify",
                            "params": envelope,
                        })
                        subs = self._client_subscriptions.get(subscribe_id)
                        if subs is not None:
                            subs.add(ws)
                        else:
                            self._client_subscriptions[subscribe_id] = {ws}
                        await ws.send(notification)

                    try:
                        result = await self._engine.dispatch(
                            method, params, sink, client_id,
                        )
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

                # Client unsubscribe notification (has method, no id)
                if role == "client" and has_method and not has_id:
                    if msg["method"] == "rois.event.unsubscribe":
                        subscribe_id = str(
                            msg.get("params", {}).get("subscribe_id", ""),
                        )
                        self._client_subscriptions.pop(subscribe_id, None)
                    continue

        except websockets.ConnectionClosed:
            pass
        finally:
            if role == "adapter" and sub_engine:
                logger.info("Adapter %s disconnected", sub_engine.engine_id)
                if sub_engine.engine_id:
                    self._engine.unregister_sub_engine(sub_engine.engine_id)
                sub_engine.detach_websocket()
                self._sub_engines.pop(ws, None)
                self._notify_profile_changed()
            if role == "client":
                if client_id:
                    self._engine.release_all(client_id)
                self._client_sockets.discard(ws)
                # Clean up this client's subscriptions
                for sub_id, subs in list(self._client_subscriptions.items()):
                    subs.discard(ws)
                    if not subs:
                        self._client_subscriptions.pop(sub_id, None)

    def _relay_event_to_clients(self, params: dict[str, Any]) -> None:
        """Relay an event notification from an adapter to subscribed clients."""
        subscribe_id = str(params.get("subscribe_id", ""))
        subs = self._client_subscriptions.get(subscribe_id)
        if subs:
            notification = json.dumps({
                "jsonrpc": "2.0",
                "method": "rois.event.notify",
                "params": params,
            })
            for ws in list(subs):
                if not ws.closed:
                    asyncio.ensure_future(ws.send(notification))