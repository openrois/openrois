"""Tests for openrois.interfaces.values, the string forms of typed values."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from openrois.interfaces import ComponentStatus, decode_value, encode_value


@pytest.mark.parametrize(
    ("data_type", "value", "text"),
    [
        ("int", 42, "42"),
        ("int", -7, "-7"),
        ("long", 0, "0"),
        ("float", 1.5, "1.5"),
        ("double", 2.0, "2.0"),
        ("bool", True, "true"),
        ("boolean", False, "false"),
        ("string", "kitchen", "kitchen"),
        ("RoISIdentifier", "reachy_real/head", "reachy_real/head"),
        ("DateTime", "2026-10-08T04:50:00+09:00", "2026-10-08T04:50:00+09:00"),
        ("Component_Status", ComponentStatus.READY, "READY"),
        ("string[]", ["kitchen", "hall"], '["kitchen", "hall"]'),
        ("String[]", ["1.5,2.0,0.0"], '["1.5,2.0,0.0"]'),
        ("int[]", [1, 2], "[1, 2]"),
        ("bool[]", [True], "[true]"),
        ("RoISIdentifier[]", [], "[]"),
        ("int[][]", [[1], [2, 3]], "[[1], [2, 3]]"),
    ],
)
def test_round_trip(data_type: str, value: object, text: str) -> None:
    """A value is written in its string form and read back as the same value."""
    assert encode_value(data_type, value) == text
    assert decode_value(data_type, text) == value


def test_float_accepts_an_int() -> None:
    assert encode_value("float", 3) == "3.0"
    assert decode_value("float", "3") == 3.0


def test_status_reads_as_the_enumeration() -> None:
    assert decode_value("Component_Status", "BUSY") is ComponentStatus.BUSY


def test_datetime_is_written_in_iso_8601() -> None:
    moment = datetime(2026, 10, 8, 4, 50, tzinfo=UTC)
    assert encode_value("DateTime", moment) == "2026-10-08T04:50:00+00:00"


def test_a_string_is_taken_as_the_string_form() -> None:
    """A str is the encoded value itself, checked against the type."""
    assert encode_value("string[]", '["home"]') == '["home"]'
    assert encode_value("int", "42") == "42"
    with pytest.raises(ValueError):
        encode_value("int", "forty-two")


def test_unknown_types_keep_their_text() -> None:
    assert decode_value("polygon", "[[0, 0], [1, 1]]") == "[[0, 0], [1, 1]]"
    assert encode_value("polygon", [[0, 0], [1, 1]]) == "[[0, 0], [1, 1]]"


@pytest.mark.parametrize(
    ("data_type", "value"),
    [
        ("int", 1.5),
        ("int", True),
        ("float", "1.5x"),
        ("bool", 1),
        ("string", 3),
        ("string[]", "kitchen"),
        ("string[]", 3),
        ("int[]", [1.5]),
        ("Component_Status", "IDLE"),
    ],
)
def test_encode_refuses_values_of_another_type(data_type: str, value: object) -> None:
    with pytest.raises(ValueError):
        encode_value(data_type, value)


# The first integer that rounds to 2**1024, which a double cannot hold, and the one below it.
ROUNDS_TO_OVERFLOW = 2**1024 - 2**970
LARGEST_THAT_FITS = ROUNDS_TO_OVERFLOW - 1


@pytest.mark.parametrize(("sign", "infinity"), [(1, math.inf), (-1, -math.inf)])
@pytest.mark.parametrize(
    "magnitude",
    [10**399, ROUNDS_TO_OVERFLOW, 10**4299],
    ids=["400 digits", "rounds to overflow", "the digit limit"],
)
def test_a_huge_integer_item_of_a_float_array_reads_as_infinity(
    sign: int, infinity: float, magnitude: int
) -> None:
    """Such an item has no float, and reads as ``[1e400]`` does in all three languages."""
    item = sign * magnitude
    assert decode_value("float[]", f"[{item}]") == [infinity]
    assert decode_value("Double[][]", f"[[{item}]]") == [[infinity]]
    assert encode_value("float[]", f"[{item}]") == f"[{item}]"


@pytest.mark.parametrize("sign", [1, -1])
def test_the_largest_integer_item_a_double_holds_stays_finite(sign: int) -> None:
    item = sign * LARGEST_THAT_FITS
    assert decode_value("float[]", f"[{item}]") == [sign * 1.7976931348623157e308]


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize(
    "magnitude",
    [2**1024, ROUNDS_TO_OVERFLOW, 10**399, 10**5000],
    ids=["2**1024", "rounds to overflow", "400 digits", "above the digit limit"],
)
@pytest.mark.parametrize(
    ("data_type", "wrap"),
    [
        ("float", lambda item: item),
        ("double", lambda item: item),
        ("float[]", lambda item: [item]),
        ("Double[][]", lambda item: [[item]]),
    ],
    ids=["float", "double", "array", "nested array"],
)
def test_encode_refuses_an_int_too_large_for_a_double(
    data_type: str, wrap: Callable[[int], object], magnitude: int, sign: int
) -> None:
    """The message is checked too, because repr of 10**5000 would raise ValueError by itself."""
    with pytest.raises(ValueError, match="a double can hold"):
        encode_value(data_type, wrap(sign * magnitude))


@pytest.mark.parametrize("sign", [1, -1])
def test_encode_keeps_the_largest_int_a_double_holds(sign: int) -> None:
    assert encode_value("float", sign * LARGEST_THAT_FITS) == repr(sign * 1.7976931348623157e308)
