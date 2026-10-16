"""Resources: what several components of one adapter share, such as a robot connection.

A resource is something the components of an adapter share: a connection to a robot, an
SDK client, a ROS 2 executor. The package that needs one ships it as a subclass of
Resource with ``open()`` and ``close()``. The adapter builds it, as it builds the
components, and hands the same object to each component that uses it, which records it
with ``Component.uses``. The engine opens the resource once, before the first component
that uses it connects, and closes it once, after the last one disconnects.

A resource reports its health with ``raise_status`` and ``clear_status``. A raised
status reaches every component that uses the resource: component_status reports it, and
the engine sends ``rois.system.notify_error`` for each of those components.
"""

from __future__ import annotations

import threading
from typing import Protocol

from openrois.interfaces.common import ComponentStatus

# The statuses a component or a resource may raise. The others follow the lifecycle.
RAISABLE = frozenset({ComponentStatus.WARNING, ComponentStatus.ERROR})


def check_raisable(status: ComponentStatus) -> None:
    """Refuse a status that only the lifecycle sets.

    Raises:
        ValueError: The status is neither WARNING nor ERROR.
    """
    if status not in RAISABLE:
        raise ValueError(f"Only WARNING or ERROR can be raised, not {status.value}")


class ResourceBinding(Protocol):
    """What a resource needs from the engine that opens it.

    The engine passes an object of this shape to ``Resource.rois_bind`` when it hosts the
    first component that uses the resource. Both methods are safe to call from any thread.
    """

    def raise_status(self, status: ComponentStatus, message: str) -> None:
        """Report WARNING or ERROR on every component that uses the resource."""
        ...

    def clear_status(self) -> None:
        """Withdraw the status the resource raised."""
        ...


class Resource:
    """Base class of something several components of one adapter share.

    Subclass it and override ``open()`` and ``close()``::

        class RobotConnection(Resource):
            async def open(self) -> None:
                self.client = RobotClient(self._host)

            async def close(self) -> None:
                await self.client.disconnect()

    ``open()`` raises only for what waiting cannot fix, such as a missing SDK or a bad
    setting: every component that uses the resource then reports ERROR and never
    connects. A robot that is not there yet is a status, raised with ``raise_status``,
    so the adapter and the robot can start in any order.
    """

    # Set by rois_bind when an engine hosts a component that uses the resource.
    _rois_binding: ResourceBinding | None = None
    # The status raised before an engine bound the resource, reported on bind.
    _rois_raised: tuple[ComponentStatus, str] | None = None
    _rois_lock: threading.Lock | None = None

    async def open(self) -> None:
        """Open what the resource holds. The default does nothing."""

    async def close(self) -> None:
        """Close what the resource holds. The default does nothing."""

    def raise_status(self, status: ComponentStatus, message: str = "") -> None:
        """Report WARNING or ERROR on every component that uses this resource.

        Safe to call from any thread, for example a watchdog or a ROS 2 callback. A
        status raised before an engine hosts the resource is reported when it does.

        Raises:
            ValueError: The status is neither WARNING nor ERROR.
        """
        check_raisable(status)
        with self._lock():
            self._rois_raised = (status, message)
            binding = self._rois_binding
        if binding is not None:
            binding.raise_status(status, message)

    def clear_status(self) -> None:
        """Withdraw the status this resource raised. Safe to call from any thread."""
        with self._lock():
            self._rois_raised = None
            binding = self._rois_binding
        if binding is not None:
            binding.clear_status()

    # -- Called by the engine ----------------------------------------------------------

    def rois_bind(self, binding: ResourceBinding) -> None:
        """Attach the engine that opens this resource, and report a raised status."""
        with self._lock():
            self._rois_binding = binding
            raised = self._rois_raised
        if raised is not None:
            binding.raise_status(*raised)

    def _lock(self) -> threading.Lock:
        # A subclass need not call __init__, so the lock is made on first use. Two
        # threads that race here could each make one, but only before the engine binds
        # the resource, when the adapter builds it on one thread.
        if self._rois_lock is None:
            self._rois_lock = threading.Lock()
        return self._rois_lock
