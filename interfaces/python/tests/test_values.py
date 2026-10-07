"""Tests for openrois.interfaces.values, the string forms of typed values."""

from __future__ import annotations

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
    ("data_type", "text"),
    [
        ("int", "1.5"),
        ("int", " 1"),
        ("int", ""),
        ("float", "fast"),
        ("bool", "True"),
        ("bool", "1"),
        ("Component_Status", "IDLE"),
        ("string[]", "home"),
        ("string[]", '{"a": 1}'),
        ("string[]", "[1]"),
        ("int[]", '["1"]'),
        ("int[]", "[true]"),
        ("bool[]", "[1]"),
    ],
)
def test_decode_refuses_text_of_another_type(data_type: str, text: str) -> None:
    with pytest.raises(ValueError):
        decode_value(data_type, text)


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
