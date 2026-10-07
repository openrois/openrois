"""Tests for the service-side method catalog (catalog.py).

The structural tests run everywhere. The IDL cross-check needs the OMG RoIS
machine-readable files (see tests/_normative.py) and checks that every params and
result model carries exactly the IDL parameter names, plus the registered extensions.
"""

from __future__ import annotations

import re
import typing

import pytest
from pydantic import BaseModel, ValidationError

import openrois.interfaces as interfaces
from openrois.interfaces.catalog import (
    EXTENSIONS,
    METHODS,
    METHODS_BY_NAME,
    NOTIFICATIONS,
    NOTIFICATIONS_BY_NAME,
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
from openrois.interfaces.hri import (
    CommandType,
    CommandUnit,
    ConcurrentCommands,
    Parameter,
    Result,
    ReturnCode,
)
from openrois.interfaces.profiles import ComponentFunction, HRIEngineProfileType
from openrois.interfaces.service import NotifyEventParams, ProfileChangedParams
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


def _extension_fields(model: type[BaseModel]) -> set[str]:
    """The fields of ``model`` that the extension registry lists."""
    return {e.field for e in EXTENSIONS if e.model == model.__name__ and e.field is not None}


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
    """get_profile carries the XSD engine profile and the profiles of its components."""

    def test_profile_is_optional_on_failure(self) -> None:
        result = GetProfileResult(return_code=ReturnCode.ERROR)
        assert result.profile is None
        assert result.component_profiles == {}

    def test_engine_profile_names_components_by_ref_only(self) -> None:
        """The XSD engine profile has no component profiles of its own."""
        assert "component_profiles" not in HRIEngineProfileType.model_fields

    def test_component_profiles_are_keyed_by_ref(self) -> None:
        result = GetProfileResult.model_validate(
            {
                "return_code": "OK",
                "profile": {
                    "identifier": {"code": "main"},
                    "component_ids": ["reachy_real/head", "reachy_sim/head"],
                },
                "component_profiles": {
                    ref: {
                        "identifier": {"authority": "OpenRoIS", "code": "Head"},
                        "name": "head",
                        "function": "actuation",
                    }
                    for ref in ("reachy_real/head", "reachy_sim/head")
                },
            }
        )
        assert result.profile is not None
        assert set(result.component_profiles) == set(result.profile.component_ids)
        head = result.component_profiles["reachy_real/head"]
        assert head.identifier.code == "Head"
        assert head.function is ComponentFunction.ACTUATION

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
# Notifications
# ---------------------------------------------------------------------------


class TestNotificationTable:
    """The notifications an engine sends: the three RoIS callbacks and one extension."""

    def test_rois_callbacks_and_the_extension(self) -> None:
        assert [(n.interface, n.operation) for n in NOTIFICATIONS] == [
            ("ServiceApplicationBase", "notify_error"),
            ("ServiceApplicationBase", "completed"),
            ("ServiceApplicationBase", "notify_event"),
            ("OpenRoIS", "profile_changed"),
        ]

    def test_names_are_unique_and_apart_from_methods(self) -> None:
        names = [n.method for n in NOTIFICATIONS]
        assert len(names) == len(set(names))
        assert not set(names) & set(METHODS_BY_NAME)

    def test_name_is_a_catalog_namespace_and_the_operation(self) -> None:
        for n in NOTIFICATIONS:
            namespace, _, operation = n.method.rpartition(".")
            assert namespace in NAMESPACES.values()
            assert operation == n.operation

    def test_index_matches_table(self) -> None:
        assert set(NOTIFICATIONS_BY_NAME) == {n.method for n in NOTIFICATIONS}
        for n in NOTIFICATIONS:
            assert NOTIFICATIONS_BY_NAME[n.method] is n

    @pytest.mark.parametrize("spec", NOTIFICATIONS, ids=lambda n: n.method)
    def test_params_are_frozen_and_closed(self, spec: object) -> None:
        model: type[BaseModel] = spec.params  # type: ignore[attr-defined]
        assert model.model_config.get("frozen") is True
        assert model.model_config.get("extra") == "forbid"

    def test_notify_event_carries_the_payload(self) -> None:
        params = NotifyEventParams.model_validate(
            {
                "event_id": "evt-1",
                "event_type": "person_detected",
                "subscribe_id": "sub-1",
                "results": [{"name": "number", "data_type_ref": "int", "value": "2"}],
            }
        )
        assert params.results == [Result(name="number", data_type_ref="int", value="2")]

    def test_notify_event_payload_is_optional(self) -> None:
        params = NotifyEventParams(event_id="evt-1", event_type="e", subscribe_id="sub-1")
        assert params.results == []

    def test_profile_changed_has_no_params(self) -> None:
        assert ProfileChangedParams.model_fields == {}
        assert ProfileChangedParams.model_validate({}) == ProfileChangedParams()
        with pytest.raises(ValidationError):
            ProfileChangedParams.model_validate({"profile": {}})


# ---------------------------------------------------------------------------
# Command types
# ---------------------------------------------------------------------------


class TestCommandTypes:
    """command_type is free text. CommandType lists the names the spec defines."""

    def test_standard_names(self) -> None:
        assert [c.value for c in CommandType] == [
            "start",
            "stop",
            "suspend",
            "resume",
            "set_parameter",
        ]

    def test_component_defined_names_are_accepted(self) -> None:
        unit = CommandUnit(component_ref="r/head", command_type="nod", command_id="c1")
        assert unit.command_type == "nod"

    def test_standard_names_serialize_as_strings(self) -> None:
        unit = CommandUnit(
            component_ref="r/head", command_type=CommandType.START, command_id="c1"
        )
        assert unit.model_dump(mode="json")["command_type"] == "start"


# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------


class TestExtensions:
    """Every extension is registered, optional and marked in its description."""

    @pytest.mark.parametrize("extension", EXTENSIONS, ids=lambda e: f"{e.model}.{e.field}")
    def test_names_a_real_model_and_field(self, extension: object) -> None:
        model = getattr(interfaces, extension.model)  # type: ignore[attr-defined]
        assert issubclass(model, BaseModel)
        if extension.field is not None:  # type: ignore[attr-defined]
            assert extension.field in model.model_fields  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "extension",
        [e for e in EXTENSIONS if e.field is not None],
        ids=lambda e: f"{e.model}.{e.field}",
    )
    def test_added_field_can_be_left_out(self, extension: object) -> None:
        """A client that ignores the field, or a sender that omits it, still works."""
        model = getattr(interfaces, extension.model)  # type: ignore[attr-defined]
        field = model.model_fields[extension.field]  # type: ignore[attr-defined]
        assert not field.is_required()
        assert "OpenRoIS extension" in (field.description or "")

    def test_whole_model_extensions_are_the_openrois_notifications(self) -> None:
        whole = {e.model for e in EXTENSIONS if e.field is None}
        openrois = {n.params.__name__ for n in NOTIFICATIONS if n.interface == "OpenRoIS"}
        assert whole == openrois

    def test_every_extension_gives_a_reason(self) -> None:
        for extension in EXTENSIONS:
            assert extension.reason.strip()

    def test_extensions_are_unique(self) -> None:
        keys = [(e.model, e.field) for e in EXTENSIONS]
        assert len(keys) == len(set(keys))


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

    def test_lists_every_notification_in_order(self) -> None:
        document = catalog_document()
        assert document["notifications"] == [
            {
                "method": n.method,
                "interface": n.interface,
                "operation": n.operation,
                "params": n.params.__name__,
            }
            for n in NOTIFICATIONS
        ]

    def test_lists_the_standard_command_types(self) -> None:
        assert catalog_document()["standard_command_types"] == [c.value for c in CommandType]

    def test_lists_error_codes_and_unmodelled_prefixes(self) -> None:
        document = catalog_document()
        assert document["json_rpc_error_codes"] == [
            {"name": c.name, "code": c.value} for c in JsonRpcErrorCode
        ]
        assert document["unmodelled_method_prefixes"] == ["rois.stream."]


# ---------------------------------------------------------------------------
# Cross-check against RoIS_HRI.idl and RoIS_Service.idl
# ---------------------------------------------------------------------------

_INTERFACE_RE = re.compile(r"interface\s+(\w+)\s*\{(.*?)\n\s*\};", re.DOTALL)
_OPERATION_RE = re.compile(r"(?:ReturnCode_t|void)\s+(\w+)\s*\((.*?)\)\s*;", re.DOTALL)
_PARAMETER_RE = re.compile(r"\b(in|out)\s+\w+\s+(\w+)")


def _idl_operations(file: str) -> dict[tuple[str, str], tuple[set[str], set[str]]]:
    """Map (interface, operation) to its in and out parameter names in an IDL file."""
    text = (NORMATIVE_DIR / file).read_text()
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
    """Every model carries the IDL parameter names and the registered extensions only."""

    def test_catalog_covers_every_idl_operation(self) -> None:
        idl = set(_idl_operations("RoIS_HRI.idl"))
        catalog = {(m.interface, m.operation) for m in METHODS}
        assert catalog == idl

    @pytest.mark.parametrize("spec", METHODS, ids=lambda m: m.method)
    def test_params_fields_are_the_in_parameters(self, spec: object) -> None:
        operations = _idl_operations("RoIS_HRI.idl")
        ins, _ = operations[(spec.interface, spec.operation)]  # type: ignore[attr-defined]
        params: type[BaseModel] = spec.params  # type: ignore[attr-defined]
        assert set(params.model_fields) == ins | _extension_fields(params)

    @pytest.mark.parametrize("spec", METHODS, ids=lambda m: m.method)
    def test_result_fields_are_return_code_and_out_parameters(self, spec: object) -> None:
        operations = _idl_operations("RoIS_HRI.idl")
        _, outs = operations[(spec.interface, spec.operation)]  # type: ignore[attr-defined]
        result: type[BaseModel] = spec.result  # type: ignore[attr-defined]
        assert set(result.model_fields) == {"return_code", *outs} | _extension_fields(result)

    def test_notifications_cover_every_callback(self) -> None:
        idl = set(_idl_operations("RoIS_Service.idl"))
        rois = {(n.interface, n.operation) for n in NOTIFICATIONS if n.interface != "OpenRoIS"}
        assert rois == idl

    @pytest.mark.parametrize(
        "spec",
        [n for n in NOTIFICATIONS if n.interface != "OpenRoIS"],
        ids=lambda n: n.method,
    )
    def test_notification_params_are_the_in_parameters(self, spec: object) -> None:
        operations = _idl_operations("RoIS_Service.idl")
        ins, outs = operations[(spec.interface, spec.operation)]  # type: ignore[attr-defined]
        assert outs == set()
        params: type[BaseModel] = spec.params  # type: ignore[attr-defined]
        assert set(params.model_fields) == ins | _extension_fields(params)
