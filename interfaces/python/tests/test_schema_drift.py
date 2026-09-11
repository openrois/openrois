"""Schema drift test — verify committed JSON Schema files match Pydantic output.

This test regenerates every schema in-memory (the same way ``export_schema.py``
does) and compares it to the committed file in ``interfaces/schema/``. If any
file is missing or its content differs, the test fails.

This is the CI guard for roadmap.md M0 Task 0.9 ("schema-drift check").

Run:  cd interfaces/python && pytest tests/test_schema_drift.py
Fix:  cd interfaces/python && python scripts/export_schema.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, TypeAdapter

from openrois.interfaces.bus import (
    CommandRequest,
    DiscoverRequest,
    DiscoverResponse,
    EventEnvelope,
    InvokeResponse,
    QueryRequest,
    QueryResponse,
    SubscribeRequest,
    SubscribeResponse,
)
from openrois.interfaces.common import ComponentStatus, StreamStatus
from openrois.interfaces.components.navigation import (
    NavigationGetParameterResult,
    NavigationReachedTargetEvent,
    NavigationSetParameter,
    NavigationSetParameterResult,
    NavigationStatusResult,
)
from openrois.interfaces.components.reaction import (
    ReactionGetParameterResult,
    ReactionSetParameter,
    ReactionSetParameterResult,
    ReactionStatusResult,
)
from openrois.interfaces.components.person_detection import (
    PersonDetectedEvent,
    PersonDetectionStatusResult,
)
from openrois.interfaces.components.person_identification import (
    PersonIdentifiedEvent,
    PersonIdentificationStatusResult,
    PersonIdentifier,
)
from openrois.interfaces.components.person_localization import (
    PersonLocalizedEvent,
    PersonLocalizationStatusResult,
    PersonPosition,
)
from openrois.interfaces.components.system_information import (
    SystemInformationEngineStatusResult,
    SystemInformationRobotPositionResult,
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

# ---------------------------------------------------------------------------
# Inventory (must match export_schema.py)
# ---------------------------------------------------------------------------

MODELS: list[type[BaseModel]] = [
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
    # bus
    DiscoverRequest,
    DiscoverResponse,
    CommandRequest,
    InvokeResponse,
    QueryRequest,
    QueryResponse,
    SubscribeRequest,
    SubscribeResponse,
    EventEnvelope,
    # components/person_detection
    PersonDetectedEvent,
    PersonDetectionStatusResult,
    # components/person_identification
    PersonIdentifiedEvent,
    PersonIdentificationStatusResult,
    PersonIdentifier,
    # components/person_localization
    PersonLocalizedEvent,
    PersonLocalizationStatusResult,
    PersonPosition,
    # components/navigation
    NavigationSetParameter,
    NavigationSetParameterResult,
    NavigationGetParameterResult,
    NavigationStatusResult,
    NavigationReachedTargetEvent,
    # components/reaction
    ReactionSetParameter,
    ReactionSetParameterResult,
    ReactionGetParameterResult,
    ReactionStatusResult,
    # components/system_information
    SystemInformationRobotPositionResult,
    SystemInformationEngineStatusResult,
]

ENUMS: list[type] = [
    ReturnCode,
    ComponentStatus,
    StreamStatus,
    CompletedStatus,
    ErrorType,
]

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

# tests/test_schema_drift.py → tests/ → python/ → interfaces/ → schema/
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_schema(cls: type) -> dict[str, object]:
    """Generate JSON Schema for a model or enum."""
    if issubclass(cls, BaseModel):
        return cls.model_json_schema()
    return TypeAdapter(cls).json_schema()


def _expected_filename(cls: type) -> str:
    """Return the expected filename for a class."""
    return f"{cls.__name__}.schema.json"


def _read_committed(name: str) -> str:
    """Read the committed schema file content."""
    path = SCHEMA_DIR / name
    return path.read_text()


def _generate_expected(cls: type) -> str:
    """Generate the expected schema content (matches export_schema.py output).

    The export script injects a ``$comment`` header into every file. The drift
    check must account for this so the comparison stays accurate.
    """
    schema = _generate_schema(cls)
    schema_with_comment: dict[str, object] = {
        "$comment": "GENERATED FROM interfaces/python: DO NOT EDIT. Run scripts/export_schema.py.",
        **schema,
    }
    return json.dumps(schema_with_comment, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSchemaDrift:
    """Verify committed schema files match Pydantic model output."""

    @pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
    def test_model_schema_matches_file(self, model: type[BaseModel]) -> None:
        """Each BaseModel's committed schema must match model_json_schema() output."""
        filename = _expected_filename(model)
        path = SCHEMA_DIR / filename
        assert path.exists(), (
            f"Schema file missing: {filename}. "
            f"Run: cd interfaces/python && python scripts/export_schema.py"
        )
        committed = _read_committed(filename)
        expected = _generate_expected(model)
        assert committed == expected, (
            f"Schema drift detected for {model.__name__}. "
            f"Run: cd interfaces/python && python scripts/export_schema.py"
        )

    @pytest.mark.parametrize("enum_cls", ENUMS, ids=lambda e: e.__name__)
    def test_enum_schema_matches_file(self, enum_cls: type) -> None:
        """Each str-Enum's committed schema must match TypeAdapter output."""
        filename = _expected_filename(enum_cls)
        path = SCHEMA_DIR / filename
        assert path.exists(), (
            f"Schema file missing: {filename}. "
            f"Run: cd interfaces/python && python scripts/export_schema.py"
        )
        committed = _read_committed(filename)
        expected = _generate_expected(enum_cls)
        assert committed == expected, (
            f"Schema drift detected for {enum_cls.__name__}. "
            f"Run: cd interfaces/python && python scripts/export_schema.py"
        )

    def test_no_extra_schema_files(self) -> None:
        """No stale schema files should exist for removed models."""
        expected_names = {
            _expected_filename(cls) for cls in [*MODELS, *ENUMS]
        }
        actual_names = {p.name for p in SCHEMA_DIR.glob("*.schema.json")}
        extra = actual_names - expected_names
        assert not extra, (
            f"Unexpected schema files (no matching model): {sorted(extra)}. "
            f"Remove them or add the corresponding Pydantic model."
        )

    def test_schema_count(self) -> None:
        """Total schema file count must match the model + enum inventory."""
        expected_count = len(MODELS) + len(ENUMS)
        actual_count = len(list(SCHEMA_DIR.glob("*.schema.json")))
        assert actual_count == expected_count, (
            f"Expected {expected_count} schema files, found {actual_count}. "
            f"Run: cd interfaces/python && python scripts/export_schema.py"
        )