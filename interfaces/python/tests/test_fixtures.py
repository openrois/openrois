"""Tests that read interfaces/fixtures, the data the TypeScript and C# packages read too.

``wire.json`` holds real gateway traffic. See ``testing/conformance/capture.py``.
"""

from __future__ import annotations

import json
import struct
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from openrois.interfaces import condition as cond
from openrois.interfaces.catalog import (
    METHODS,
    METHODS_BY_NAME,
    NOTIFICATIONS,
    NOTIFICATIONS_BY_NAME,
    ExecuteParams,
)
from openrois.interfaces.hri import CommandUnit, ConcurrentCommands
from openrois.interfaces.profiles import RoISIdentifierType
from openrois.interfaces.values import decode_value, encode_value

type Entry = dict[str, Any]

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

BUILDERS: dict[str, Callable[..., str]] = {
    "quote": cond.quote,
    "eq": cond.eq,
    "like": cond.like,
    "all_of": cond.all_of,
    "component_ref": cond.component_ref,
    "component_type": cond.component_type,
    "component_type_urn": cond.component_type_urn,
}


def load(name: str) -> list[Entry]:
    entries: list[Entry] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return entries


WIRE = load("wire.json")
CONDITIONS = load("conditions.json")
VALUES = load("values.json")

LANGUAGE = "python"
EDGES: dict[str, list[Entry]] = json.loads(
    (FIXTURES / "value-edges.json").read_text(encoding="utf-8")
)


def case_key(case: Entry) -> str:
    """The fields of a case or of an exception's reference, compared as one text."""
    fields = ("data_type", "text", "value_text", "name")
    return json.dumps({field: case[field] for field in fields if field in case})


def excepted(list_name: str) -> set[str]:
    """The cases of a list that value-edges.json records as a difference of this language."""
    return {
        case_key(case)
        for exception in EDGES["exceptions"]
        if exception["language"] == LANGUAGE
        for case in exception["cases"]
        if case["list"] == list_name
    }


def edge_cases(list_name: str) -> list[Entry]:
    """The cases of a list that hold in this language."""
    skipped = excepted(list_name)
    return [case for case in EDGES[list_name] if case_key(case) not in skipped]


def typed(data_type: str, value: object) -> object:
    """A ``value`` column as a Python value. A float JSON cannot carry is its text there."""
    if isinstance(value, list):
        item_type = data_type.removesuffix("[]")
        return [typed(item_type, item) for item in value]
    if isinstance(value, str) and data_type.lower() in ("float", "double"):
        return float(value)
    return value


def check_refused(case: Entry) -> None:
    try:
        decoded = decode_value(case["data_type"], case["text"])
    except ValueError:
        return
    raise AssertionError(f"Read {decoded!r}")


def check_decoded(case: Entry) -> None:
    decoded = decode_value(case["data_type"], case["text"])
    # The JSON text tells 2.0 from 2, -0.0 from 0.0 and NaN from itself, which == does not.
    assert json.dumps(decoded) == json.dumps(typed(case["data_type"], case["value"]))


def check_encoded(case: Entry) -> None:
    # json.loads reads every form the column uses: NaN, Infinity, -0.0 and a whole integer.
    assert encode_value(case["data_type"], json.loads(case["value_text"])) == case["text"]


def check_model(case: Entry) -> None:
    model = wire_model(case)
    try:
        model.model_validate(case["body"])
    except ValidationError:
        assert case["refused"]
        return
    assert not case["refused"]


def check_condition(case: Entry) -> None:
    assert BUILDERS[case["builder"]](*case["args"]) == case["expected"]


EDGE_CHECKS: dict[str, Callable[[Entry], None]] = {
    "refused": check_refused,
    "decoded": check_decoded,
    "encoded": check_encoded,
    "models": check_model,
    "conditions": check_condition,
}


def wire_model(entry: Entry) -> type[BaseModel]:
    """The catalog model of a recorded body."""
    if entry["kind"] == "notification":
        return NOTIFICATIONS_BY_NAME[entry["method"]].params
    spec = METHODS_BY_NAME[entry["method"]]
    return spec.params if entry["kind"] == "params" else spec.result


class TestWire:
    @pytest.mark.parametrize(
        "entry", WIRE, ids=[f"{i}-{e['kind']}-{e['method']}" for i, e in enumerate(WIRE)]
    )
    def test_body_round_trips(self, entry: Entry) -> None:
        model = wire_model(entry).model_validate(entry["body"])
        assert model.model_dump(mode="json") == entry["body"]

    @pytest.mark.parametrize("kind", ["params", "result"])
    def test_every_method_is_recorded(self, kind: str) -> None:
        recorded = {e["method"] for e in WIRE if e["kind"] == kind}
        assert recorded == {spec.method for spec in METHODS}

    def test_every_notification_is_recorded(self) -> None:
        recorded = {e["method"] for e in WIRE if e["kind"] == "notification"}
        assert recorded == {spec.method for spec in NOTIFICATIONS}

    def test_execute_params_hold_a_command_and_a_group(self) -> None:
        [body] = [
            e["body"]
            for e in WIRE
            if e["kind"] == "params" and e["method"] == "rois.command.execute"
        ]
        items = ExecuteParams.model_validate(body).command_unit_list
        assert {type(item) for item in items} == {CommandUnit, ConcurrentCommands}


class TestConditions:
    @pytest.mark.parametrize("vector", CONDITIONS, ids=lambda v: f"{v['builder']}-{v['expected']}")
    def test_builder(self, vector: Entry) -> None:
        args = [
            RoISIdentifierType.model_validate(arg) if isinstance(arg, dict) else arg
            for arg in vector["args"]
        ]
        assert BUILDERS[vector["builder"]](*args) == vector["expected"]

    def test_every_builder_has_a_vector(self) -> None:
        assert {v["builder"] for v in CONDITIONS} == set(BUILDERS)


class TestValues:
    @pytest.mark.parametrize("vector", VALUES, ids=lambda v: f"{v['data_type']}-{v['text']}")
    def test_encode(self, vector: Entry) -> None:
        assert encode_value(vector["data_type"], vector["value"]) == vector["text"]

    @pytest.mark.parametrize("vector", VALUES, ids=lambda v: f"{v['data_type']}-{v['text']}")
    def test_decode(self, vector: Entry) -> None:
        decoded = decode_value(vector["data_type"], vector["text"])
        # The JSON text tells 2.0 from 2 and true from 1, which == does not.
        assert json.dumps(decoded) == json.dumps(vector["value"])

    def test_every_type_family_has_a_vector(self) -> None:
        names = {v["data_type"].removesuffix("[]").lower() for v in VALUES}
        assert names >= {
            "int",
            "integer",
            "long",
            "short",
            "float",
            "double",
            "bool",
            "boolean",
            "component_status",
            "string",
            "roisidentifier",
            "datetime",
        }

    @pytest.mark.parametrize("family", ["int", "float", "bool", "string"])
    def test_every_array_family_has_a_vector(self, family: str) -> None:
        assert any(v["data_type"].lower() == f"{family}[]" for v in VALUES)


class TestValueEdges:
    @pytest.mark.parametrize("case", edge_cases("refused"), ids=case_key)
    def test_refused(self, case: Entry) -> None:
        check_refused(case)

    @pytest.mark.parametrize("case", edge_cases("decoded"), ids=case_key)
    def test_decoded(self, case: Entry) -> None:
        check_decoded(case)

    @pytest.mark.parametrize("case", edge_cases("encoded"), ids=case_key)
    def test_encoded(self, case: Entry) -> None:
        check_encoded(case)

    @pytest.mark.parametrize("case", edge_cases("models"), ids=case_key)
    def test_model(self, case: Entry) -> None:
        check_model(case)

    @pytest.mark.parametrize("case", edge_cases("conditions"), ids=case_key)
    def test_condition(self, case: Entry) -> None:
        check_condition(case)

    @pytest.mark.parametrize("case", EDGES["doubles"], ids=lambda c: c["text"])
    def test_double_encodes(self, case: Entry) -> None:
        number = struct.unpack(">d", bytes.fromhex(case["bits"]))[0]
        assert encode_value("double", number) == case["text"]

    @pytest.mark.parametrize("case", EDGES["doubles"], ids=lambda c: c["text"])
    def test_double_decodes(self, case: Entry) -> None:
        assert struct.pack(">d", decode_value("double", case["text"])).hex() == case["bits"]

    @pytest.mark.parametrize(
        ("list_name", "key"),
        [
            (case["list"], case_key(case))
            for exception in EDGES["exceptions"]
            for case in exception["cases"]
        ],
    )
    def test_exception_names_a_case(self, list_name: str, key: str) -> None:
        assert key in {case_key(case) for case in EDGES[list_name]}

    @pytest.mark.parametrize(
        ("list_name", "case"),
        [
            (name, case)
            for name in EDGE_CHECKS
            for case in EDGES[name]
            if case_key(case) in excepted(name)
        ],
        ids=lambda v: v if isinstance(v, str) else case_key(v),
    )
    def test_exception_is_still_a_difference(self, list_name: str, case: Entry) -> None:
        """A difference that went away must leave the file, or it would hide a regression."""
        with pytest.raises((ValueError, AssertionError)):
            EDGE_CHECKS[list_name](case)
