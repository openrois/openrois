"""The errors of the OpenRoIS Python client SDK.

RoISError reports an operation the engine ran and refused. Everything else that goes
wrong between the client and the engine is a TransportError or one of its subclasses,
so a caller can catch the base class or a specific failure:

    RoISError                The engine answered with a return code other than OK.
    TransportError           The base of the three below, and a call on a closed client.
    RoISConnectionError      The WebSocket cannot be opened, or closes while a request waits.
    RequestTimeoutError      No reply arrived within the request timeout.
    RpcError                 The engine answered with a JSON-RPC error.

Parameters that fail validation raise ``pydantic.ValidationError`` before anything is sent.
"""

from __future__ import annotations

from openrois.interfaces import ReturnCode


class RoISError(Exception):
    """Raised when a RoIS operation returns a code other than OK.

    A RoIS failure is a normal result on the wire, so this error carries the return code
    for callers to branch on.

    Attributes:
        return_code: The return code of the result.
        method: The JSON-RPC method that returned it.
    """

    def __init__(self, return_code: ReturnCode, method: str) -> None:
        super().__init__(f"{method} failed with {return_code}")
        self.return_code = return_code
        self.method = method


class TransportError(Exception):
    """The base of every failure below the RoIS operations."""


class RoISConnectionError(TransportError, ConnectionError):
    """Raised when the WebSocket cannot be opened or is lost.

    It is not named ConnectionError, which would shadow the builtin, and it inherits the
    builtin so that ``except ConnectionError`` in calling code keeps working.

    Attributes:
        url: The URL the transport tried to reach.
    """

    def __init__(self, message: str, url: str = "") -> None:
        super().__init__(message)
        self.url = url


class RequestTimeoutError(TransportError, TimeoutError):
    """Raised when a request gets no reply in time.

    It inherits the builtin so that ``except TimeoutError`` in calling code keeps working.

    Attributes:
        method: The JSON-RPC method that timed out.
        request_id: The id of the request.
    """

    def __init__(self, method: str, request_id: str, timeout: float) -> None:
        super().__init__(f"Request timed out after {timeout}s: {method} (id: {request_id})")
        self.method = method
        self.request_id = request_id


class RpcError(TransportError):
    """Raised when the engine answers with a JSON-RPC error object.

    This reports a protocol fault: unparseable JSON, an invalid request, an unknown method,
    params that fail validation, or an internal error. A RoIS failure is not an RpcError: it
    is a normal result with a return code other than OK, which the client raises as RoISError.

    Attributes:
        code: The JSON-RPC error code, for example -32601 for an unknown method.
        data: The additional data of the error, or None.
    """

    def __init__(self, code: int, message: str, data: object = None) -> None:
        super().__init__(f"RPC error {code}: {message}")
        self.code = code
        self.data = data
