"""The notifications an agent has not read yet, behind a cursor.

MCP answers requests and RoIS pushes notifications, so the server keeps them here and an
agent reads them between tool calls, or waits for one.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Entry:
    """One notification, numbered in arrival order from 1.

    Attributes:
        seq: The cursor of this entry. get_events after it returns the ones that follow.
        kind: event, error, completed, profile_changed, connection_closed or idle_release.
        time: When the server received it, in ISO 8601.
        data: The notification, as JSON values.
    """

    seq: int
    kind: str
    time: str
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "kind": self.kind, "time": self.time, **self.data}


class EventBuffer:
    """A bounded buffer of notifications. The oldest go first when it is full."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._entries: deque[Entry] = deque(maxlen=capacity)
        self._last = 0
        self._changed = asyncio.Event()

    @property
    def last(self) -> int:
        """The cursor of the newest entry, or 0 when nothing arrived yet."""
        return self._last

    def append(self, kind: str, data: dict[str, Any]) -> Entry:
        """Add a notification and wake every waiter."""
        self._last += 1
        entry = Entry(self._last, kind, datetime.now(UTC).isoformat(), data)
        self._entries.append(entry)
        # A fresh Event per change lets each waiter look again without missing one that
        # lands while it checks.
        changed, self._changed = self._changed, asyncio.Event()
        changed.set()
        return entry

    def since(self, cursor: int, limit: int) -> tuple[list[Entry], int, int]:
        """The entries after a cursor.

        Returns:
            The entries, at most ``limit``, the cursor to pass next time, and how many
            entries after the cursor were dropped because the buffer was full.
        """
        oldest = self._entries[0].seq if self._entries else self._last + 1
        dropped = max(0, oldest - cursor - 1)
        found = [entry for entry in self._entries if entry.seq > cursor][: max(0, limit)]
        next_cursor = found[-1].seq if found else max(cursor, oldest - 1)
        return found, next_cursor, dropped

    async def wait_for(
        self, cursor: int, match: Callable[[Entry], bool], timeout: float
    ) -> Entry | None:
        """Wait for the first entry after a cursor that matches.

        Returns:
            The entry, or None when the timeout passes first.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        seen = cursor
        while True:
            for entry in self._entries:
                if entry.seq > seen:
                    seen = entry.seq
                    if match(entry):
                        return entry
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            changed = self._changed
            try:
                await asyncio.wait_for(changed.wait(), remaining)
            except TimeoutError:
                return None
