"""The decorators that declare a component and its handlers.

``@component(profile)`` declares which RoIS component type a Component subclass is. The
method decorators mark the messages it implements:

- ``@invoke(command_type)``: a command, run for as long as the command lasts.
- ``@query(query_type)``: a query.
- ``@subscribe(event_type)``: an event the component emits. The method runs on each new
  subscription to it.
- ``@on_set_parameter``: the hook that applies new parameter values.

The engine serves the part of the profile the class implements, so a client never sees a
message the component does not answer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openrois.interfaces.profiles import HRIComponentProfile

from openrois.components.core._spec import HANDLER_ATTRIBUTE, Handler, HandlerKind, build_spec
from openrois.components.core.component import Component


def component[C: Component](profile: HRIComponentProfile) -> Callable[[type[C]], type[C]]:
    """Declare a Component subclass as a component of the type ``profile`` describes.

    Pass a profile constant from ``openrois.interfaces.components`` for a basic component,
    for example ``NAVIGATION_PROFILE``, or a full HRIComponentProfile of your own. The
    handlers are checked against the profile when the class is defined.

    Raises:
        TypeError: The decorated class is not a Component subclass, or a handler has the
            wrong form.
        ValueError: A handler names a message the profile does not define.
    """
    if not isinstance(profile, HRIComponentProfile):
        raise TypeError(
            "@component takes an HRIComponentProfile, for example NAVIGATION_PROFILE, "
            f"not {type(profile).__name__}"
        )

    def declare(cls: type[C]) -> type[C]:
        if not (isinstance(cls, type) and issubclass(cls, Component)):
            raise TypeError(f"@component declares a subclass of Component, not {cls!r}")
        cls.__rois_spec__ = build_spec(cls, profile)
        return cls

    return declare


def invoke[F: Callable[..., Any]](command_type: str) -> Callable[[F], F]:
    """Mark an async method as the handler of a command, for example ``start``."""
    return _mark("command", command_type)


def query[F: Callable[..., Any]](query_type: str) -> Callable[[F], F]:
    """Mark an async method as the handler of a query, for example ``robot_position``."""
    return _mark("query", query_type)


def subscribe[F: Callable[..., Any]](event_type: str) -> Callable[[F], F]:
    """Mark an event the component emits, for example ``reached_target``.

    The async method runs on each new subscription to the event, for example to start a
    detector. It may do nothing when the component emits the event on its own.
    """
    return _mark("event", event_type)


def on_set_parameter[F: Callable[..., Any]](method: F) -> F:
    """Mark the async method that applies new parameter values.

    The method receives the new values by name, converted from their profile types,
    before the engine stores them. It applies them to the backend, or raises to refuse
    them, and the engine then keeps the old values.
    """
    return _mark("set_parameter", "")(method)


def _mark[F: Callable[..., Any]](kind: HandlerKind, name: str) -> Callable[[F], F]:
    def mark(method: F) -> F:
        if hasattr(method, HANDLER_ATTRIBUTE):
            where = getattr(method, "__qualname__", repr(method))
            raise ValueError(f"{where} already handles a message")
        setattr(method, HANDLER_ATTRIBUTE, Handler(kind, name))
        return method

    return mark
