"""Tests for openrois.interfaces.type_codes, the data_type_ref table (stream I, step 2).

Validation rows 7 and 33: the profiles name types by short codes. Each known code maps
to a Python type, and an unknown code keeps its string and maps to Any.
"""

from __future__ import annotations

from typing import Any

import pytest
from lxml import etree

from openrois.interfaces.common import ComponentStatus, StreamStatus
from openrois.interfaces.hri import DateTime, RoISIdentifier
from openrois.interfaces.type_codes import TYPE_CODES, python_type
from tests._normative import NORMATIVE_DIR, requires_normative

PROFILE_FILES = sorted(
    p.name for p in NORMATIVE_DIR.glob("*.xml") if p.name != "Model.xml"
) if NORMATIVE_DIR.is_dir() else []


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("string", str),
        ("String", str),
        ("int", int),
        ("bool", bool),
        ("RoISIdentifier", RoISIdentifier),
        ("DateTime", DateTime),
        ("Component_Status", ComponentStatus),
        ("Stream_Status", StreamStatus),
        ("string[]", list[str]),
        ("String[]", list[str]),
        ("int[]", list[int]),
        ("RoISIdentifier[]", list[RoISIdentifier]),
    ],
)
def test_known_code(code: str, expected: object) -> None:
    assert python_type(code) == expected


def test_table_holds_the_twelve_codes() -> None:
    assert set(TYPE_CODES) == {
        "string",
        "String",
        "int",
        "bool",
        "string[]",
        "String[]",
        "int[]",
        "RoISIdentifier",
        "RoISIdentifier[]",
        "DateTime",
        "Component_Status",
        "Stream_Status",
    }


def test_string_is_case_insensitive() -> None:
    assert python_type("STRING") is str
    assert python_type("sTrInG[]") == list[str]


@pytest.mark.parametrize(
    "code",
    ["Boolean", "Double", "Set<String>", "NbestType", "urn:x-rois:def:DataType:ATR::Integer", ""],
)
def test_unknown_code_maps_to_any(code: str) -> None:
    assert python_type(code) is Any


def test_unknown_array_maps_to_a_list_of_any() -> None:
    assert python_type("Double[]") == list[Any]


@requires_normative
def test_every_code_in_the_profiles_is_known() -> None:
    """Every data_type_ref code the 18 profiles use is in the table."""
    used: set[str] = set()
    # recover: FaceLocalization.xml declares the RoIS namespace with a trailing space.
    parser = etree.XMLParser(recover=True)
    for filename in PROFILE_FILES:
        root = etree.parse(str(NORMATIVE_DIR / filename), parser).getroot()
        for ref in root.iter():
            if isinstance(ref.tag, str) and etree.QName(ref).localname == "data_type_ref":
                used.update(v for k, v in ref.attrib.items() if k.endswith("}code"))
    assert len(PROFILE_FILES) == 18
    assert used == set(TYPE_CODES)
