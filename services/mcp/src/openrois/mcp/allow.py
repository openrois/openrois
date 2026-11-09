"""Which components an agent may act on, by CQL2 LIKE patterns on their refs."""

from __future__ import annotations

import re
from collections.abc import Iterable


def like_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a CQL2 LIKE pattern: ``%`` is any run of characters, ``_`` one character.

    A backslash takes the next character literally, so ``\\%`` matches a percent sign.
    """
    parts: list[str] = []
    escaped = False
    for char in pattern:
        if escaped:
            parts.append(re.escape(char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "%":
            parts.append(".*")
        elif char == "_":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    if escaped:
        parts.append(re.escape("\\"))
    return re.compile("".join(parts), re.DOTALL)


class AllowFilter:
    """The components an agent may bind, configure and command.

    With no pattern, every component is allowed.
    """

    def __init__(self, patterns: Iterable[str] = ()) -> None:
        self.patterns = tuple(patterns)
        self._compiled = [like_pattern(pattern) for pattern in self.patterns]

    def allows(self, component_ref: str) -> bool:
        """Whether an agent may act on the component."""
        if not self._compiled:
            return True
        return any(pattern.fullmatch(component_ref) for pattern in self._compiled)

    def describe(self) -> str:
        """The patterns, for a refusal message."""
        if not self.patterns:
            return "every component"
        return ", ".join(repr(pattern) for pattern in self.patterns)
