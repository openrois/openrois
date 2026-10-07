"""JSON-RPC 2.0 over WebSocket: the framing of the method catalog, for server and client.

:func:`answer` turns one message from a peer into its reply. Faults that never reach a
RoIS operation are JSON-RPC errors, as the method catalog defines them:

- JSON that does not parse is PARSE_ERROR, with a null id.
- An object that is not a request is INVALID_REQUEST.
- A method outside the catalog is METHOD_NOT_FOUND, every ``rois.stream.*`` included.
- Params that fail the catalog model are INVALID_PARAMS, with the issues as data.
- An engine that fails while it handles the request is INTERNAL_ERROR.

A message without an id is a notification and gets no reply. A RoIS operation that runs
and fails answers a normal result whose ``return_code`` is not OK.

:class:`Outbox` sends the messages of one connection in the order they were put. A
request's reply is put before any notification it causes, for example the
``rois.command.completed`` of a set_parameter, so the peer always reads the reply first.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from openrois.interfaces.catalog import METHODS_BY_NAME, JsonRpcErrorCode
from pydantic import BaseModel, ValidationError
from websockets.asyncio.connection import Connection
from websockets.exceptions import ConnectionClosed

from openrois.engine.engine import Engine
from openrois.engine.session import Session

logger = logging.getLogger(__name__)

JSONRPC_VERSION = "2.0"


async def answer(engine: Engine, session: Session, raw: str | bytes) -> str | None:
    """The reply to one message from the peer of a session, or None for a notification."""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return _error(None, JsonRpcErrorCode.PARSE_ERROR, "Parse error: invalid JSON")
    if isinstance(payload, dict) and "method" in payload and "id" not in payload:
        return None
    if not _is_request(payload):
        return _error(
            _id_of(payload),
            JsonRpcErrorCode.INVALID_REQUEST,
            "Invalid Request: not a valid JSON-RPC 2.0 request",
        )
    request_id = payload["id"]
    method: str = payload["method"]
    spec = METHODS_BY_NAME.get(method)
    if spec is None:
        return _error(request_id, JsonRpcErrorCode.METHOD_NOT_FOUND, f"Method not found: {method}")
    raw_params = payload.get("params")
    try:
        params = spec.params.model_validate({} if raw_params is None else raw_params)
    except ValidationError as exc:
        issues = [
            {"path": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return _error(
            request_id, JsonRpcErrorCode.INVALID_PARAMS, f"Invalid params for {method}", issues
        )
    try:
        result = await engine.handle(session, method, params)
        body = result.model_dump(mode="json")
    except Exception:
        logger.exception("The engine failed on %s", method)
        return _error(request_id, JsonRpcErrorCode.INTERNAL_ERROR, "Internal error")
    return json.dumps({"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": body})


async def serve_session(
    engine: Engine, session: Session, outbox: Outbox, connection: Connection
) -> None:
    """Answer the requests on a connection, each in its own task, until it closes.

    Then cancel the requests still running, close the session and stop the outbox.
    """
    tasks: set[asyncio.Task[None]] = set()

    async def reply(raw: str | bytes) -> None:
        try:
            message = await answer(engine, session, raw)
        except Exception:
            logger.exception("Could not answer a message")
            return
        if message is not None:
            outbox.put(message)

    try:
        async for raw in connection:
            task = asyncio.create_task(reply(raw))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
    except ConnectionClosed:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.close_session(session)
        await outbox.close()


async def send_text(connection: Connection, message: str) -> None:
    """Send a message, ignoring a peer that has already gone."""
    try:
        await connection.send(message)
    except ConnectionClosed:
        logger.debug("Dropped a message for a closed connection.")


def notification(method: str, params: BaseModel) -> str:
    """A notification message: a method and its params, with no id."""
    return json.dumps(
        {"jsonrpc": JSONRPC_VERSION, "method": method, "params": params.model_dump(mode="json")}
    )


class Outbox:
    """The messages waiting to go out on one connection, sent in the order they were put.

    :meth:`put` never waits, so the engine can call :meth:`notify` from its callbacks
    and the order of the messages is the order of the calls. Create the outbox on the
    event loop of the connection.
    """

    def __init__(self, send: Callable[[str], Awaitable[None]]) -> None:
        """Start the writer of a connection.

        Args:
            send: Sends one text message. It returns without raising when the peer
                has gone, so the writer keeps draining the queue.
        """
        self._send = send
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._writer = asyncio.create_task(self._write())

    def put(self, message: str) -> None:
        """Queue one message."""
        self._queue.put_nowait(message)

    def notify(self, method: str, params: BaseModel) -> None:
        """Queue one notification. A session sends its notifications through this."""
        self.put(notification(method, params))

    async def close(self) -> None:
        """Stop the writer. Messages still queued are dropped with the connection."""
        self._writer.cancel()
        await asyncio.gather(self._writer, return_exceptions=True)

    async def _write(self) -> None:
        while True:
            message = await self._queue.get()
            try:
                await self._send(message)
            except Exception:
                logger.exception("Could not send a message")


def _error(
    request_id: Any, code: JsonRpcErrorCode, message: str, data: Any = None
) -> str:
    error: dict[str, Any] = {"code": int(code), "message": message}
    if data is not None:
        error["data"] = data
    return json.dumps({"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error})


def _is_id(value: object) -> bool:
    """Whether a value is a valid JSON-RPC id: a string, a number, or null."""
    return value is None or (isinstance(value, (str, int, float)) and not isinstance(value, bool))


def _id_of(payload: object) -> Any:
    """The id of a message that is not a valid request, when it has a valid one."""
    if isinstance(payload, dict) and _is_id(payload.get("id")):
        return payload.get("id")
    return None


def _is_request(payload: object) -> bool:
    """Whether a payload is a JSON-RPC 2.0 request object with an id."""
    return (
        isinstance(payload, dict)
        and payload.get("jsonrpc") == JSONRPC_VERSION
        and isinstance(payload.get("method"), str)
        and "id" in payload
        and _is_id(payload["id"])
    )
