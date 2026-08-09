"""Event emission for OpenRoIS adapters.

The EventEmitter manages event subscriptions and provides a thread-safe
emit() method. The framework creates one EventEmitter per adapter and
sets it on the adapter instance as adapter.emit.

The roboticist calls self.emit("object_detected", results.detection(...))
from a ROS 2 callback or any async context. The framework handles
subscribe_id generation, sink routing, and unsubscribe cleanup.

If nobody is subscribed to an event type, emit() is a no-op.
"""

from __future__ import annotations

import asyncio
import json
import uuid
import logging
import uuid
from collections.abc import Awaitable, Callable

from openrois.interfaces.hri import Result

logger = logging.getLogger(__name__)


class EventEmitter:
    """Manages event subscriptions and thread-safe event emission.

    The framework creates one EventEmitter and sets it on the adapter
    instance. The roboticist calls adapter.emit(event_type, results)
    to push events to all subscribed operators.

    Attributes:
        _subscribers: Maps (component_ref, event_type) to a list of
            (subscribe_id, component_ref, event_type) tuples.
        _ws_send: Async callable that sends a raw JSON string over the WS.
        _loop: The asyncio event loop (for thread-safe scheduling).
    """

    def __init__(
        self,
        ws_send: Callable[[str], Awaitable[None]],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Initialize the EventEmitter.

        Args:
            ws_send: Async callable that sends a raw JSON string over the WS.
            loop: The asyncio event loop (for thread-safe emit from rclpy).
        """
        self._ws_send = ws_send
        self._loop = loop
        # subscribe_id -> (component_ref, event_type)
        self._subscriptions: dict[str, tuple[str, str]] = {}

    def add_subscription(self, component_ref: str, event_type: str) -> str:
        """Register a new subscription and return the subscribe_id.

        Called by the framework when the avatar sends rois.event.subscribe.

        Args:
            component_ref: The component ref (without fleet_id prefix).
            event_type: The event type name.

        Returns:
            A unique subscribe_id string.
        """
        subscribe_id = f"sub-{uuid.uuid4().hex[:8]}"
        self._subscriptions[subscribe_id] = (component_ref, event_type)
        logger.debug(
            "Subscribed %s for %s/%s (%d total)",
            subscribe_id,
            component_ref,
            event_type,
            len(self._subscriptions),
        )
        return subscribe_id

    def remove_subscription(self, subscribe_id: str) -> bool:
        """Remove a subscription by subscribe_id.

        Called by the framework when the avatar sends rois.event.unsubscribe.

        Args:
            subscribe_id: The subscription ID to remove.

        Returns:
            True if the subscription was found and removed, False otherwise.
        """
        removed = self._subscriptions.pop(subscribe_id, None)
        if removed:
            logger.debug(
                "Unsubscribed %s (%d remaining)",
                subscribe_id,
                len(self._subscriptions),
            )
        return removed is not None

    def remove_all_subscriptions(self) -> None:
        """Remove all subscriptions. Called on WS disconnect."""
        self._subscriptions.clear()

    def has_subscribers(self, component_ref: str, event_type: str) -> bool:
        """Check if there are active subscribers for a component/event pair."""
        return any(
            (cref, etype) == (component_ref, event_type)
            for cref, etype in self._subscriptions.values()
        )

    def emit(
        self,
        component_ref: str,
        event_type: str,
        results: list[Result],
    ) -> None:
        """Emit an event to all subscribed operators.

        Thread-safe: can be called from a rclpy callback in a background
        thread. Uses asyncio.run_coroutine_threadsafe() to schedule the
        WS send on the main asyncio loop.

        If nobody is subscribed to this (component_ref, event_type),
        this is a no-op.

        Args:
            component_ref: The component ref (without fleet_id prefix).
            event_type: The event type name.
            results: The event payload as a list of Result models.
        """
        matching = [
            sid
            for sid, (cref, etype) in self._subscriptions.items()
            if cref == component_ref and etype == event_type
        ]
        if not matching:
            return

        for subscribe_id in matching:
            notification = {
                "jsonrpc": "2.0",
                "method": "rois.event.notify",
                "params": {
                    "event_id": str(uuid.uuid4()),
                    "subscribe_id": subscribe_id,
                    "component_ref": component_ref,
                    "event_type": event_type,
                    "expire": "",
                    "results": [r.model_dump() for r in results],
                },
            }
            msg = json.dumps(notification)
            # Thread-safe: schedule the send on the main loop.
            asyncio.run_coroutine_threadsafe(
                self._ws_send(msg),
                self._loop,
            )

    def emit_async(
        self,
        component_ref: str,
        event_type: str,
        results: list[Result],
    ) -> Awaitable[None]:
        """Async version of emit() for use within the asyncio loop.

        Use this from async context (e.g., inside an async handler).
        Use emit() from sync context (e.g., rclpy callbacks).

        Args:
            component_ref: The component ref (without fleet_id prefix).
            event_type: The event type name.
            results: The event payload as a list of Result models.
        """
        matching = [
            sid
            for sid, (cref, etype) in self._subscriptions.items()
            if cref == component_ref and etype == event_type
        ]
        if not matching:
            # Return a completed coroutine-like object.
            return _noop()  # type: ignore[return-value]

        async def _send_all() -> None:
            for subscribe_id in matching:
                notification = {
                    "jsonrpc": "2.0",
                    "method": "rois.event.notify",
                    "params": {
                        "event_id": str(uuid.uuid4()),
                        "subscribe_id": subscribe_id,
                        "component_ref": component_ref,
                        "event_type": event_type,
                        "expire": "",
                        "results": [r.model_dump() for r in results],
                    },
                }
                msg = json.dumps(notification)
                await self._ws_send(msg)

        return _send_all()


async def _noop() -> None:
    """No-op coroutine for emit_async when there are no subscribers."""
    pass
