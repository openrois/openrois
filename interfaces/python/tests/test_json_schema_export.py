"""Tests for JSON Schema export from Pydantic models."""

import json

from pydantic import TypeAdapter

from openrois.interfaces.common import ComponentStatus, StreamStatus
from openrois.interfaces.components.navigation import (
    NavigationGetParameterResult,
    NavigationReachedTargetEvent,
    NavigationSetParameter,
    NavigationSetParameterResult,
    NavigationStatusResult,
)
from openrois.interfaces.components.person_detection import (
    PersonDetectedEvent,
    PersonDetectionStatusResult,
)
from openrois.interfaces.hri import (
    Argument,
    CommandUnit,
    CommandUnitSequence,
    ConcurrentCommands,
    Parameter,
    Result,
    ReturnCode,
)
from openrois.interfaces.profiles import (
    CommandMessageProfile,
    EventMessageProfile,
    HRIComponentProfile,
    HRIEngineProfileType,
    MessageProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from openrois.interfaces.service import (
    CompletedEvent,
    CompletedStatus,
    ErrorType,
    NotifyErrorEvent,
    NotifyEventPayload,
)

# Models (BaseModel subclasses) that support model_json_schema()
BASE_MODELS = [
    # hri
    Result,
    Parameter,
    Argument,
    CommandUnit,
    ConcurrentCommands,
    CommandUnitSequence,
    # service
    NotifyErrorEvent,
    CompletedEvent,
    NotifyEventPayload,
    # profiles
    RoISIdentifierType,
    ParameterProfile,
    MessageProfile,
    CommandMessageProfile,
    QueryMessageProfile,
    EventMessageProfile,
    HRIComponentProfile,
    HRIEngineProfileType,
    # person_detection
    PersonDetectedEvent,
    PersonDetectionStatusResult,
    # navigation
    NavigationSetParameter,
    NavigationSetParameterResult,
    NavigationGetParameterResult,
    NavigationStatusResult,
    NavigationReachedTargetEvent,
]

# String enums (str, Enum) — need TypeAdapter for schema generation
STRING_ENUMS = [
    ReturnCode,
    ComponentStatus,
    StreamStatus,
    CompletedStatus,
    ErrorType,
]


class TestJsonSchemaExport:
    """Verify that all models can produce valid JSON Schema."""

    def test_all_models_produce_schema(self) -> None:
        """Every BaseModel subclass should produce a non-empty JSON Schema dict."""
        for model in BASE_MODELS:
            schema = model.model_json_schema()
            assert isinstance(schema, dict), f"{model.__name__} schema is not a dict"
            assert "properties" in schema or "$defs" in schema, (
                f"{model.__name__} schema missing properties or $defs"
            )

    def test_schema_is_valid_json(self) -> None:
        """All model schemas should be JSON-serializable."""
        for model in BASE_MODELS:
            schema = model.model_json_schema()
            json_str = json.dumps(schema)
            assert isinstance(json_str, str)
            parsed = json.loads(json_str)
            assert isinstance(parsed, dict)

    def test_enum_schema_has_values(self) -> None:
        """String enums should list their values in the schema via TypeAdapter."""
        for enum_cls in STRING_ENUMS:
            adapter = TypeAdapter(enum_cls)
            schema = adapter.json_schema()
            assert "enum" in schema, f"{enum_cls.__name__} missing 'enum' key"
            values = schema["enum"]
            assert len(values) == len(list(enum_cls)), (
                f"{enum_cls.__name__} schema enum count mismatch: "
                f"got {len(values)}, expected {len(list(enum_cls))}"
            )

    def test_struct_schema_has_required_fields(self) -> None:
        """Struct-like models should list required fields."""
        # Result has three required fields: name, data_type_ref, value
        schema = Result.model_json_schema()
        assert "required" in schema
        assert "name" in schema["required"]
        assert "value" in schema["required"]

        # CommandUnit has required fields: command_type, arguments
        schema = CommandUnit.model_json_schema()
        assert "required" in schema
        assert "command_type" in schema["required"]

    def test_schema_title_matches_model_name(self) -> None:
        """Schema title should match the Pydantic model class name."""
        for model in BASE_MODELS:
            schema = model.model_json_schema()
            # For recursive models, Pydantic v2 may put the title inside $defs
            # and use a $ref at the top level (no title key).
            title = schema.get("title")
            if title is None and "$defs" in schema:
                title = schema["$defs"].get(model.__name__, {}).get("title")
            assert title == model.__name__, (
                f"{model.__name__} schema title mismatch: {title}"
            )

    def test_enum_schema_title_matches_name(self) -> None:
        """Enum schema title should match the enum class name."""
        for enum_cls in STRING_ENUMS:
            adapter = TypeAdapter(enum_cls)
            schema = adapter.json_schema()
            assert schema.get("title") == enum_cls.__name__, (
                f"{enum_cls.__name__} schema title mismatch: {schema.get('title')}"
            )

    def test_frozen_models_have_no_extra(self) -> None:
        """Frozen models should forbid extra fields (model config extra='forbid')."""
        frozen_models = [
            NotifyErrorEvent,
            CompletedEvent,
            NotifyEventPayload,
            PersonDetectedEvent,
            NavigationSetParameterResult,
            NavigationReachedTargetEvent,
        ]
        for model in frozen_models:
            # Verify via model_config rather than JSON Schema,
            # since Pydantic v2 doesn't always emit additionalProperties=False
            # at the top level when $defs are present.
            assert model.model_config.get("frozen") is True, (
                f"{model.__name__} should have frozen=True"
            )
            assert model.model_config.get("extra") == "forbid", (
                f"{model.__name__} should have extra='forbid'"
            )
