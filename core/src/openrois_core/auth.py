"""Authentication and authorization for the gateway.

Clients present a JSON Web Token at the WebSocket upgrade, in an
``Authorization: Bearer`` header or, for browsers, a ``token`` query parameter.
The token's ``roles`` claim decides which RoIS operations the connection may
call, and its optional ``scope`` claim limits which component refs it may see
and address. Nothing here changes the RoIS interfaces: a call outside the
caller's rights answers with the ``ERROR`` return code and a ``notify_error``.

Roles, from the least to the most permissive:

- ``viewer``: connect, read profiles, query, subscribe to events.
- ``maintenance``: the viewer's rights (scope it to SystemInformation components).
- ``operator``: the viewer's rights plus reservations, parameters, and commands.
- ``administrator``: every operation.
- ``adapter``: may connect on the ``/adapter`` path and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any
from urllib.parse import parse_qs, urlsplit

import jwt

READ_METHODS = frozenset({
    "rois.system.connect",
    "rois.system.disconnect",
    "rois.system.get_profile",
    "rois.system.get_error_detail",
    "rois.command.search",
    "rois.command.get_parameter",
    "rois.command.get_command_result",
    "rois.query.query",
    "rois.event.subscribe",
    "rois.event.unsubscribe",
    "rois.event.get_event_detail",
})
CONTROL_METHODS = frozenset({
    "rois.command.bind",
    "rois.command.bind_any",
    "rois.command.release",
    "rois.command.set_parameter",
    "rois.command.execute",
})
STREAM_METHODS = frozenset({
    "rois.stream.connect_stream",
    "rois.stream.disconnect_stream",
    "rois.stream.suspend_stream",
    "rois.stream.resume_stream",
    "rois.stream.query_stream_status",
})

ROLE_METHODS: dict[str, frozenset[str]] = {
    "viewer": READ_METHODS | STREAM_METHODS,
    "maintenance": READ_METHODS,
    "operator": READ_METHODS | CONTROL_METHODS | STREAM_METHODS,
    "administrator": READ_METHODS | CONTROL_METHODS | STREAM_METHODS,
    "adapter": frozenset(),
}


class AuthError(Exception):
    """A token is missing, invalid, expired, or carries no usable role."""


@dataclass(frozen=True)
class Principal:
    """Who is on the other end of a connection, as the token describes it."""

    subject: str
    roles: frozenset[str]
    # Component ref patterns (fnmatch) the principal may see. ("*",) means all.
    scope: tuple[str, ...] = ("*",)

    def may_call(self, method: str) -> bool:
        return any(method in ROLE_METHODS.get(role, frozenset()) for role in self.roles)

    def may_see(self, component_ref: str) -> bool:
        return any(fnmatch(component_ref, pattern) for pattern in self.scope)

    @property
    def is_adapter(self) -> bool:
        return "adapter" in self.roles or "administrator" in self.roles


@dataclass(frozen=True)
class AuthConfig:
    """How the gateway verifies tokens.

    ``key`` is the shared secret for HMAC algorithms or the public key (PEM) for
    asymmetric ones. ``issuer`` and ``audience`` are checked when set.
    """

    key: str
    algorithms: tuple[str, ...] = ("HS256",)
    issuer: str | None = None
    audience: str | None = None
    leeway_seconds: int = 30
    required_claims: tuple[str, ...] = field(default=("exp", "sub"))

    def decode(self, token: str) -> Principal:
        """Verify a token and turn its claims into a Principal."""
        options: Any = {"require": list(self.required_claims)}
        if not self.audience:
            options["verify_aud"] = False
        try:
            claims = jwt.decode(
                token,
                self.key,
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway_seconds,
                options=options,
            )
        except jwt.PyJWTError as exc:
            raise AuthError(str(exc)) from exc
        roles = claims.get("roles", [])
        if isinstance(roles, str):
            roles = [roles]
        known = frozenset(r for r in roles if r in ROLE_METHODS)
        if not known:
            raise AuthError("token carries no known role")
        scope = claims.get("scope", ["*"])
        if isinstance(scope, str):
            scope = scope.split()
        return Principal(
            subject=str(claims.get("sub", "")),
            roles=known,
            scope=tuple(str(s) for s in scope) or ("*",),
        )


def token_from(headers: Any, path: str) -> str | None:
    """Extract a bearer token from the upgrade headers or the URL query."""
    authorization = ""
    try:
        authorization = str(headers.get("Authorization", "") or "")
    except Exception:
        authorization = ""
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    query = parse_qs(urlsplit(path).query)
    values = query.get("token") or query.get("access_token")
    return values[0] if values else None
