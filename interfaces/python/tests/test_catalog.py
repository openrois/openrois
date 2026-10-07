"""Tests for the service-side method catalog (catalog.py).

The structural tests run everywhere. The IDL cross-check needs the OMG RoIS
machine-readable files (see tests/_normative.py) and checks that every params and
result model carries exactly the IDL parameter names.
"""

from __future__ import annotations

import re
import typing

import pytest
from pydantic import BaseModel, ValidationError

from openrois.interfaces.catalog import (
    METHODS,
    METHODS_BY_NAME,
    STREAMING_METHOD_PREFIX,
    CommandIF,
    EventIF,
    ExecuteParams,
    GetParameterResult,
    GetProfileResult,
    JsonRpcErrorCode,
    QueryIF,
    SetParameterParams,
    SystemIF,
    catalog_document,
)
from openrois.interfaces.hri import CommandUnit, ConcurrentCommands, Parameter, ReturnCode
from tests._normative import NORMATIVE_DIR, requires_normative

PROTOCOLS: dict[str, type] = {
    "SystemIF": SystemIF,
    "CommandIF": CommandIF,
    "QueryIF": QueryIF,
    "EventIF": EventIF,
}

NAMESPACES: dict[str, str] = {
    "SystemIF": "rois.system",
    "CommandIF": "rois.command",
    "QueryIF": "rois.query",
    "EventIF": "rois.event",
}


def _protocol_methods(protocol: type) -> set[str]:
    """Names of the methods a Protocol declares, without inherited ones."""
    return {
        name
        for name, value in vars(protocol).items()
        if callable(value) and not name.startswith("_")
    }


# ---------------------------------------------------------------------------
# Method table
# ---------------------------------------------------------------------------


class TestMethodTable:
    """The method table is complete, consistent and indexed."""

    def test_sixteen_methods(self) -> None:
        """SystemIF 4, CommandIF 8, QueryIF 1 and EventIF 3 operations."""
        assert len(METHODS) == 16

    def test_method_names_are_unique(self) -> None:
        names = [m.method for m in METHODS]
        assert len(names) == len(set(names))

    def test_method_name_is_namespace_and_operation(self) -> None:
        for m in METHODS:
            assert m.method == f"{NAMESPACES[m.interface]}.{m.operation}"

    def test_streaming_is_not_modelled(self) -> None:
        assert not any(m.method.startswith(STREAMING_METHOD_PREFIX) for m in METHODS)

    def test_index_matches_table(self) -> None:
        assert set(METHODS_BY_NAME) == {m.method for m in METHODS}
        for m in METHODS:
            assert METHODS_BY_NAME[m.method] is m

    def test_model_names_follow_the_operation(self) -> None:
        """ExecuteParams and ExecuteResult for execute, and so on."""
        for m in METHODS:
            stem = "".join(part.capitalize() for part in m.operation.split("_"))
            assert m.params.__name__ == f"{stem}Params"
            assert m.result.__name__ == f"{stem}Result"


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class TestProtocols:
    """Each Protocol declares exactly its interface's operations, typed by the table."""

    @pytest.mark.parametrize("interface", sorted(PROTOCOLS))
    def test_protocol_declares_the_operations(self, interface: str) -> None:
        expected = {m.operation for m in METHODS if m.interface == interface}
        assert _protocol_methods(PROTOCOLS[interface]) == expected

    @pytest.mark.parametrize("spec", METHODS, ids=lambda m: m.method)
    def test_protocol_method_signature(self, spec: object) -> None:
        protocol = PROTOCOLS[spec.interface]  # type: ignore[attr-defined]
        hints = typing.get_type_hints(getattr(protocol, spec.operation))  # type: ignore[attr-defined]
        assert hints["params"] is spec.params  # type: ignore[attr-defined]
        assert hints["return"] is spec.result  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestModels:
    """Shared rules for every params and result model."""

    @pytest.mark.parametrize("spec", METHODS, ids=lambda m: m.method)
    def test_result_needs_only_return_code(self, spec: object) -> None:
        """Out parameters default to empty values for failure results."""
        result = spec.result.model_validate({"return_code": "ERROR"})  # type: ignore[attr-defined]
        assert result.return_code is ReturnCode.ERROR

    @pytest.mark.parametrize("spec", METHODS, ids=lambda m: m.method)
    def test_extra_fields_are_rejected(self, spec: object) -> None:
        model: type[BaseModel] = spec.result  # type: ignore[attr-defined]
        with pytest.raises(ValidationError):
            model.model_validate({"return_code": "OK", "unexpected": 1})

    @pytest.mark.parametrize("spec", METHODS, ids=lambda m: m.method)
    def test_models_are_frozen(self, spec: object) -> None:
        for model in (spec.params, spec.result):  # type: ignore[attr-defined]
            assert model.model_config.get("frozen") is True
            assert model.model_config.get("extra") == "forbid"


class TestExecute:
    """execute carries the CommandUnitSequence and returns only a return code."""

    def test_sequential_and_concurrent_units(self) -> None:
        params = ExecuteParams.model_validate(
            {
                "command_unit_list": [
                    {
                        "component_ref": "reachy_real/head",
                        "command_type": "start",
                        "command_id": "nod-1",
                    },
                    {
                        "command_list": [
                            {
                                "component_ref": "reachy_real/head",
                                "command_type": "stop",
                                "command_id": "nod-2",
                            },
                            {
                                "component_ref": "reachy_sim/head",
                                "command_type": "stop",
                                "command_id": "nod-3",
                            },
                        ],
                        "delay_time": 500,
                    },
                ]
            }
        )
        first, second = params.command_unit_list
        assert isinstance(first, CommandUnit)
        assert first.command_id == "nod-1"
        assert isinstance(second, ConcurrentCommands)
        assert [c.command_id for c in second.command_list] == ["nod-2", "nod-3"]

    def test_round_trip(self) -> None:
        unit = CommandUnit(component_ref="r/head", command_type="start", command_id="c1")
        params = ExecuteParams(command_unit_list=[unit])
        assert ExecuteParams.model_validate_json(params.model_dump_json()) == params

    def test_empty_list_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecuteParams(command_unit_list=[])

    def test_command_id_is_required_on_each_unit(self) -> None:
        with pytest.raises(ValidationError):
            ExecuteParams.model_validate(
                {"command_unit_list": [{"component_ref": "r/head", "command_type": "start"}]}
            )

    def test_no_top_level_component_ref(self) -> None:
        with pytest.raises(ValidationError):
            ExecuteParams.model_validate(
                {
                    "component_ref": "r/head",
                    "command_unit_list": [
                        {"component_ref": "r/head", "command_type": "start", "command_id": "c"}
                    ],
                }
            )


class TestParameters:
    """get_parameter returns parameters and set_parameter returns a command id."""

    def test_get_parameter_returns_parameters(self) -> None:
        result = GetParameterResult.model_validate(
            {
                "return_code": "OK",
                "parameters": [{"name": "time_limit", "data_type_ref": "int", "value": "30"}],
            }
        )
        assert result.parameters == [Parameter(name="time_limit", data_type_ref="int", value="30")]

    def test_get_parameter_has_no_results_field(self) -> None:
        assert "results" not in GetParameterResult.model_fields

    def test_set_parameter_params(self) -> None:
        params = SetParameterParams(
            component_ref="r/nav",
            parameters=[Parameter(name="time_limit", data_type_ref="int", value="30")],
        )
        assert SetParameterParams.model_validate(params.model_dump()) == params


class TestGetProfile:
    """get_profile carries the structured engine profile."""

    def test_profile_is_optional_on_failure(self) -> None:
        assert GetProfileResult(return_code=ReturnCode.ERROR).profile is None

    def test_profile_validates(self) -> None:
        result = GetProfileResult.model_validate(
            {
                "return_code": "OK",
                "profile": {"identifier": {"code": "main"}, "component_ids": ["r/head"]},
            }
        )
        assert result.profile is not None
        assert result.profile.component_ids == ["r/head"]


# ---------------------------------------------------------------------------
# Error codes and the catalog document
# ---------------------------------------------------------------------------


class TestJsonRpcErrorCode:
    def test_standard_values(self) -> None:
        assert JsonRpcErrorCode.PARSE_ERROR == -32700
        assert JsonRpcErrorCode.INVALID_REQUEST == -32600
        assert JsonRpcErrorCode.METHOD_NOT_FOUND == -32601
        assert JsonRpcErrorCode.INVALID_PARAMS == -32602
        assert JsonRpcErrorCode.INTERNAL_ERROR == -32603


class TestCatalogDocument:
    def test_lists_every_method_in_order(self) -> None:
        document = catalog_document()
        methods = typing.cast(list[dict[str, str]], document["methods"])
        assert [entry["method"] for entry in methods] == [m.method for m in METHODS]
        for entry, m in zip(methods, METHODS, strict=True):
            assert entry == {
                "method": m.method,
                "interface": m.interface,
                "operation": m.operation,
                "params": m.params.__name__,
                "result": m.result.__name__,
            }

    def test_lists_error_codes_and_unmodelled_prefixes(self) -> None:
        document = catalog_document()
        assert document["json_rpc_error_codes"] == [
            {"name": c.name, "code": c.value} for c in JsonRpcErrorCode
        ]
        assert document["unmodelled_method_prefixes"] == ["rois.stream."]


# ---------------------------------------------------------------------------
# Cross-check against RoIS_HRI.idl
# ---------------------------------------------------------------------------

_INTERFACE_RE = re.compile(r"interface\s+(\w+)\s*\{(.*?)\n\s*\};", re.DOTALL)
_OPERATION_RE = re.compile(r"ReturnCode_t\s+(\w+)\s*\((.*?)\)\s*;", re.DOTALL)
_PARAMETER_RE = re.compile(r"\b(in|out)\s+\w+\s+(\w+)")


def _idl_operations() -> dict[tuple[str, str], tuple[set[str], set[str]]]:
    """Map (interface, operation) to its in and out parameter names in RoIS_HRI.idl."""
    text = (NORMATIVE_DIR / "RoIS_HRI.idl").read_text()
    operations: dict[tuple[str, str], tuple[set[str], set[str]]] = {}
    for interface, body in _INTERFACE_RE.findall(text):
        for operation, parameters in _OPERATION_RE.findall(body):
            ins: set[str] = set()
            outs: set[str] = set()
            for direction, name in _PARAMETER_RE.findall(parameters):
                (ins if direction == "in" else outs).add(name)
            operations[(interface, operation)] = (ins, outs)
    return operations


@requires_normative
class TestIdlCrossCheck:
    """Every model carries exactly the IDL parameter names. No field is invented."""

    def test_catalog_covers_every_idl_operation(self) -> None:
        idl = set(_idl_operations())
        catalog = {(m.interface, m.operation) for m in METHODS}
        assert catalog == idl

    @pytest.mark.parametrize("spec", METHODS, ids=lambda m: m.method)
    def test_params_fields_are_the_in_parameters(self, spec: object) -> None:
        ins, _ = _idl_operations()[(spec.interface, spec.operation)]  # type: ignore[attr-defined]
        assert set(spec.params.model_fields) == ins  # type: ignore[attr-defined]

    @pytest.mark.parametrize("spec", METHODS, ids=lambda m: m.method)
    def test_result_fields_are_return_code_and_out_parameters(self, spec: object) -> None:
        _, outs = _idl_operations()[(spec.interface, spec.operation)]  # type: ignore[attr-defined]
        assert set(spec.result.model_fields) == {"return_code", *outs}  # type: ignore[attr-defined]
