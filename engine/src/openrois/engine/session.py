"""A connection that sends requests to an engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

#: Sends one notification to the peer of a session: the method name and its params.
type Notify = Callable[[str, BaseModel], None]


@dataclass(eq=False)
class Session:
    """A client of an engine, or the parent engine of an adapter.

    Bindings and subscriptions belong to a session, and the engine releases them
    when the session closes. A command sends its ``rois.command.completed`` to the
    session that started it.

    Attributes:
        id: Unique within the engine.
        notify: Sends a notification to the peer. Called on the event loop thread, and
            never blocks.
        trusted: Whether the peer is the parent engine of this one. A parent checked
            the bindings of a request before it forwarded it, so the engine does not
            check them again.
    """

    id: str
    notify: Notify
    trusted: bool = False
