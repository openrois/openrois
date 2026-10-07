"""The filter language of every ``condition`` parameter.

RoIS types a condition as ``Condition_t``, a string that carries an ISO 19143 filter
expression. OpenRoIS keeps it a string and writes the filter in a subset of CQL2-Text,
the text encoding of the OGC Common Query Language (OGC 21-065r2). CQL2 grew out of
the OGC Filter Encoding standard that ISO 19143 is based on, and its text form is
readable by people and by tools.

The subset:

    condition   = [ comparison *( "AND" comparison ) ]
    comparison  = property ( "=" / "LIKE" ) literal
    property    = identifier / DQUOTE identifier DQUOTE
    literal     = "'" *( character / "''" ) "'"

  - An empty condition is no filter.
  - Keywords are accepted in any case and written in upper case.
  - Inside a literal, a single quote is written twice: ``'it''s'``.
  - In a LIKE pattern, ``%`` matches any run of characters, ``_`` matches one
    character, and a backslash makes the next character literal. Matching is
    case-sensitive.
  - OR, NOT, parentheses and the other CQL2 operators are not part of the subset.

Properties a condition may use:

  - ``component_ref``: the fully qualified ref of a component, ``engine_id/ref``.
  - ``component_type``: the URN of the component's profile identifier, for example
    ``urn:x-rois:def:component:OMG::PersonDetection``.

Both select components. They apply to search, bind_any, get_profile, query and
subscribe. No property is defined yet for the result filters of get_error_detail,
get_command_result and get_event_detail, so those conditions must be empty. An engine
answers a condition it cannot parse, or one that uses a property the method does not
support, with ReturnCode.BAD_PARAMETER.

This module parses and evaluates conditions, and builds them with correct quoting.

Source: OGC Common Query Language (CQL2), 21-065r2, requirements for CQL2-Text and
the LIKE predicate.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from openrois.interfaces.profiles import RoISIdentifierType

# The property that selects a component by its fully qualified ref.
COMPONENT_REF = "component_ref"

# The property that selects components by the URN of their profile identifier.
COMPONENT_TYPE = "component_type"

# The properties a component selection may use.
SELECTION_PROPERTIES: frozenset[str] = frozenset({COMPONENT_REF, COMPONENT_TYPE})

type Operator = Literal["=", "LIKE"]


class ConditionError(ValueError):
    """Raised when a condition is not valid in the OpenRoIS subset of CQL2-Text."""


@dataclass(frozen=True, slots=True)
class Comparison:
    """One comparison of a property with a literal.

    Attributes:
        property: The property name.
        operator: ``=`` or ``LIKE``.
        value: The literal, or the LIKE pattern, without its quotes.
    """

    property: str
    operator: Operator
    value: str

    def matches(self, properties: Mapping[str, str]) -> bool:
        """Whether the property values satisfy this comparison.

        A property that is missing from ``properties`` never matches.
        """
        actual = properties.get(self.property)
        if actual is None:
            return False
        if self.operator == "=":
            return actual == self.value
        return _like_regex(self.value).fullmatch(actual) is not None

    def __str__(self) -> str:
        return f"{self.property} {self.operator} {quote(self.value)}"


@dataclass(frozen=True, slots=True)
class Condition:
    """A parsed condition: every comparison must hold.

    Attributes:
        comparisons: The comparisons joined by AND. Empty means no filter.
    """

    comparisons: tuple[Comparison, ...] = ()

    def matches(self, properties: Mapping[str, str]) -> bool:
        """Whether the property values satisfy every comparison."""
        return all(c.matches(properties) for c in self.comparisons)

    def equal_values(self, property_name: str) -> set[str]:
        """The values the condition requires ``property_name`` to equal.

        Routing uses this to go straight to the components a condition names.
        """
        return {
            c.value
            for c in self.comparisons
            if c.property == property_name and c.operator == "="
        }

    def __str__(self) -> str:
        return " AND ".join(str(c) for c in self.comparisons)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<string>'(?:[^']|'')*')
      | (?P<quoted>"[A-Za-z_:][A-Za-z0-9_.:]*")
      | (?P<word>[A-Za-z_:][A-Za-z0-9_.:]*)
      | (?P<equals>=)
      | (?P<other>\S)
    )
    """,
    re.VERBOSE,
)


def _tokens(text: str) -> list[tuple[str, str, int]]:
    """Split a condition into (kind, text, position) tokens."""
    tokens: list[tuple[str, str, int]] = []
    position = 0
    while position < len(text):
        if text[position:].strip() == "":
            break
        match = _TOKEN_RE.match(text, position)
        if match is None or match.lastgroup is None:
            raise ConditionError(f"Cannot read the condition at position {position}.")
        kind = match.lastgroup
        value = match.group(kind)
        start = match.start(kind)
        if kind == "other":
            if value == "'":
                raise ConditionError(f"Unterminated string literal at position {start}.")
            raise ConditionError(f"Unexpected character {value!r} at position {start}.")
        tokens.append((kind, value, start))
        position = match.end()
    return tokens


def parse_condition(
    text: str,
    allowed_properties: frozenset[str] = SELECTION_PROPERTIES,
) -> Condition:
    """Parse a condition in the OpenRoIS subset of CQL2-Text.

    Args:
        text: The condition. Empty or blank means no filter.
        allowed_properties: The properties the calling method supports.

    Raises:
        ConditionError: The text is not in the subset, or names a property that is not
            in ``allowed_properties``.
    """
    tokens = _tokens(text)
    comparisons: list[Comparison] = []
    index = 0
    while index < len(tokens):
        if comparisons:
            kind, value, position = tokens[index]
            if kind == "word" and value.upper() in {"OR", "NOT"}:
                raise ConditionError(
                    f"{value.upper()} at position {position} is not part of the OpenRoIS "
                    "subset. Only AND joins comparisons."
                )
            if kind != "word" or value.upper() != "AND":
                raise ConditionError(
                    f"Expected AND at position {position}. Only AND joins comparisons."
                )
            index += 1
        if index + 3 > len(tokens):
            raise ConditionError("A comparison needs a property, an operator and a literal.")
        (p_kind, p_value, p_pos), (o_kind, o_value, o_pos), (l_kind, l_value, l_pos) = tokens[
            index : index + 3
        ]
        if p_kind == "quoted":
            name = p_value[1:-1]
        elif p_kind == "word" and p_value.upper() not in {"AND", "LIKE", "OR", "NOT"}:
            name = p_value
        else:
            raise ConditionError(f"Expected a property name at position {p_pos}.")
        if name not in allowed_properties:
            supported = ", ".join(sorted(allowed_properties)) or "none"
            raise ConditionError(f"Unsupported property {name!r}. Supported: {supported}.")
        operator: Operator
        if o_kind == "equals":
            operator = "="
        elif o_kind == "word" and o_value.upper() == "LIKE":
            operator = "LIKE"
        else:
            raise ConditionError(f"Expected = or LIKE at position {o_pos}.")
        if l_kind != "string":
            raise ConditionError(f"Expected a quoted literal at position {l_pos}.")
        literal = l_value[1:-1].replace("''", "'")
        if operator == "LIKE":
            _like_regex(literal)
        comparisons.append(Comparison(name, operator, literal))
        index += 3
    return Condition(tuple(comparisons))


def _like_regex(pattern: str) -> re.Pattern[str]:
    """Translate a LIKE pattern into an anchored regular expression."""
    parts: list[str] = []
    escaped = False
    for character in pattern:
        if escaped:
            parts.append(re.escape(character))
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "%":
            parts.append(".*")
        elif character == "_":
            parts.append(".")
        else:
            parts.append(re.escape(character))
    if escaped:
        raise ConditionError("A LIKE pattern cannot end with an escape character.")
    return re.compile("".join(parts), re.DOTALL)


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def quote(value: str) -> str:
    """Write ``value`` as a CQL2 string literal, doubling any single quote."""
    return "'" + value.replace("'", "''") + "'"


def eq(property_name: str, value: str) -> str:
    """Build ``property = 'value'``."""
    return str(Comparison(property_name, "=", value))


def like(property_name: str, pattern: str) -> str:
    """Build ``property LIKE 'pattern'``. The pattern keeps its wildcards."""
    return str(Comparison(property_name, "LIKE", pattern))


def all_of(*conditions: str) -> str:
    """Join conditions with AND, skipping empty ones."""
    return " AND ".join(c for c in conditions if c.strip())


def component_type_urn(identifier: RoISIdentifierType) -> str:
    """The ``component_type`` value of a component profile identifier.

    ``RoISIdentifierType(authority="OMG", code="PersonDetection")`` gives
    ``urn:x-rois:def:component:OMG::PersonDetection``, the form the spec's component
    profiles use.
    """
    return f"urn:x-rois:def:component:{identifier.authority}::{identifier.code}"
