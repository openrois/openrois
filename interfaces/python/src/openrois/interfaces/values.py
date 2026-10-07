"""How a typed RoIS value travels as a string.

The IDL types the value of a Result, a Parameter and an Argument as ``any`` and names its
type in ``data_type_ref``. OpenRoIS carries every value as a string (``Result.value``,
``Parameter.value``, ``Argument.value``) and writes it by the rules below, so an engine
can check a value against its profile and a component can read it as a Python value.

- ``int``, ``integer``, ``long``, ``short``: an ``int``, written in decimal (``42``).
- ``float``, ``double``: a ``float`` (``1.5``).
- ``bool``, ``boolean``: a ``bool``, written ``true`` or ``false``.
- ``Component_Status``: a ``ComponentStatus``, written as its name (``READY``).
- ``string``, ``RoISIdentifier``, ``DateTime`` and any other type: a ``str``, written as
  the text itself. A ``datetime`` is written in ISO 8601.
- ``<type>[]``: a ``list`` of ``<type>``, written as a JSON array.

Type names are matched without regard to case, so ``String[]`` and ``string[]`` are the
same type. An array holds its items as JSON values: numbers for the numeric types,
``true`` and ``false`` for the boolean types, and strings for every other type, for
example ``["kitchen", "hall"]`` for ``string[]``.

Source: OMG RoIS Framework 2.0, RoIS_HRI.idl (``any value``). The string forms are an
OpenRoIS choice, described in section 17 of docs/rois-reference.md.
"""

from __future__ import annotations

import json
from datetime import datetime

from openrois.interfaces.common import ComponentStatus

# Type names by the Python value they carry, lowercased.
_INTEGER = frozenset({"int", "integer", "long", "short"})
_FLOAT = frozenset({"float", "double"})
_BOOLEAN = frozenset({"bool", "boolean"})
_STATUS = "component_status"

_ARRAY_SUFFIX = "[]"


def encode_value(data_type: str, value: object) -> str:
    """Write a value of the type ``data_type`` as its string form.

    A ``str`` is taken as the string form itself and is checked against the type. A
    ``datetime`` is written in ISO 8601. A value of a type this module does not know is
    written as JSON, unless it is already a ``str``.

    Args:
        data_type: The ``data_type_ref`` code, for example ``int`` or ``string[]``.
        value: The value to write.

    Returns:
        The string form of the value.

    Raises:
        ValueError: The value does not fit the type.
    """
    if isinstance(value, str):
        decode_value(data_type, value)
        return value
    base = data_type.lower()
    if base.endswith(_ARRAY_SUFFIX):
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"A {data_type} value must be a list, not {type(value).__name__}")
        item_type = data_type[: -len(_ARRAY_SUFFIX)]
        return json.dumps([_to_json(item_type, item) for item in value], ensure_ascii=False)
    item = _to_json(data_type, value)
    if isinstance(item, bool):
        return "true" if item else "false"
    if isinstance(item, str):
        return item
    return json.dumps(item, ensure_ascii=False)


def decode_value(data_type: str, text: str) -> object:
    """Read the string form of a value of the type ``data_type``.

    Args:
        data_type: The ``data_type_ref`` code, for example ``int`` or ``string[]``.
        text: The string form, as it travels in ``Result.value``.

    Returns:
        The value: an ``int``, ``float``, ``bool``, ``ComponentStatus``, ``str``, or a
        ``list`` of those for an array type.

    Raises:
        ValueError: The text is not a value of the type.
    """
    base = data_type.lower()
    if base.endswith(_ARRAY_SUFFIX):
        try:
            items = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"A {data_type} value must be a JSON array: {text!r}") from exc
        if not isinstance(items, list):
            raise ValueError(f"A {data_type} value must be a JSON array: {text!r}")
        item_type = data_type[: -len(_ARRAY_SUFFIX)]
        return [_from_json(item_type, item) for item in items]
    if base in _INTEGER:
        if text.strip() != text or not text.lstrip("-").isdigit():
            raise ValueError(f"Not a {data_type} value: {text!r}")
        return int(text)
    if base in _FLOAT:
        try:
            return float(text)
        except ValueError as exc:
            raise ValueError(f"Not a {data_type} value: {text!r}") from exc
    if base in _BOOLEAN:
        if text not in ("true", "false"):
            raise ValueError(f"A {data_type} value must be true or false: {text!r}")
        return text == "true"
    if base == _STATUS:
        try:
            return ComponentStatus(text)
        except ValueError as exc:
            raise ValueError(f"Not a {data_type} name: {text!r}") from exc
    return text


def _to_json(data_type: str, value: object) -> object:
    """The JSON value that stands for ``value``, as one item or one scalar."""
    base = data_type.lower()
    if base.endswith(_ARRAY_SUFFIX):
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"A {data_type} value must be a list, not {type(value).__name__}")
        item_type = data_type[: -len(_ARRAY_SUFFIX)]
        return [_to_json(item_type, item) for item in value]
    if base in _INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"A {data_type} value must be an int, not {value!r}")
        return value
    if base in _FLOAT:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"A {data_type} value must be a number, not {value!r}")
        return float(value)
    if base in _BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError(f"A {data_type} value must be a bool, not {value!r}")
        return value
    if base == _STATUS:
        if not isinstance(value, str):
            raise ValueError(f"A {data_type} value must be a ComponentStatus, not {value!r}")
        return ComponentStatus(value).value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    if base in ("string", "roisidentifier", "datetime"):
        raise ValueError(f"A {data_type} value must be a str, not {type(value).__name__}")
    return value


def _from_json(data_type: str, item: object) -> object:
    """The value that one JSON item of an array stands for."""
    base = data_type.lower()
    if base.endswith(_ARRAY_SUFFIX):
        if not isinstance(item, list):
            raise ValueError(f"A {data_type} item must be a JSON array: {item!r}")
        item_type = data_type[: -len(_ARRAY_SUFFIX)]
        return [_from_json(item_type, inner) for inner in item]
    if base in _INTEGER:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"A {data_type} item must be a JSON integer: {item!r}")
        return item
    if base in _FLOAT:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"A {data_type} item must be a JSON number: {item!r}")
        return float(item)
    if base in _BOOLEAN:
        if not isinstance(item, bool):
            raise ValueError(f"A {data_type} item must be true or false: {item!r}")
        return item
    if not isinstance(item, str):
        raise ValueError(f"A {data_type} item must be a JSON string: {item!r}")
    return decode_value(data_type, item)
