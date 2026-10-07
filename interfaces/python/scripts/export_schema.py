"""Export all Pydantic models and str-Enums to interfaces/schema/*.schema.json.

This script is the canonical generator for the JSON Schema wire contract.
Run it whenever a Pydantic model or enum changes:

    cd interfaces/python
    python scripts/export_schema.py

The output directory is ``interfaces/schema/`` (sibling of ``interfaces/python/``).
Each model produces one file named ``<ClassName>.schema.json``.

- ``BaseModel`` subclasses → ``model_json_schema()``
- ``str, Enum`` classes    → ``TypeAdapter(cls).json_schema()``

The CI drift check (``tests/test_schema_drift.py``) verifies that committed
schema files match this script's output, preventing silent drift.

Source: roadmap.md M0 Task 0.5
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from openrois.interfaces.catalog import METHODS, catalog_document
from openrois.interfaces.contract import (
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
from openrois.interfaces.components import profiles_document
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
    ComponentFunction,
    EventMessageProfile,
    HRIComponentProfile,
    HRIEngineProfileType,
    MessageProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from openrois.interfaces.service import (
    CompletedParams,
    CompletedStatus,
    ErrorType,
    NotifyErrorParams,
    NotifyEventParams,
    ProfileChangedParams,
)

# ---------------------------------------------------------------------------
# Inventory: every exportable type
# ---------------------------------------------------------------------------

# The catalog's params and result models, in method table order.
CATALOG_MODELS: list[type[BaseModel]] = [cls for m in METHODS for cls in (m.params, m.result)]

# BaseModel subclasses → model_json_schema()
MODELS: list[type[BaseModel]] = [
    # hri
    Result,
    Parameter,
    Argument,
    CommandUnit,
    ConcurrentCommands,
    CommandUnitSequence,
    # service
    NotifyErrorParams,
    CompletedParams,
    NotifyEventParams,
    ProfileChangedParams,
    # profiles
    RoISIdentifierType,
    ParameterProfile,
    MessageProfile,
    CommandMessageProfile,
    QueryMessageProfile,
    EventMessageProfile,
    HRIComponentProfile,
    HRIEngineProfileType,
    # contract
    DiscoverRequest,
    DiscoverResponse,
    CommandRequest,
    InvokeResponse,
    QueryRequest,
    QueryResponse,
    SubscribeRequest,
    SubscribeResponse,
    EventEnvelope,
    # catalog
    *CATALOG_MODELS,
    # components/person_detection
    PersonDetectedEvent,
    PersonDetectionStatusResult,
    # components/navigation
    NavigationSetParameter,
    NavigationSetParameterResult,
    NavigationGetParameterResult,
    NavigationStatusResult,
    NavigationReachedTargetEvent,    # components/reaction
    ReactionSetParameter,
    ReactionSetParameterResult,
    ReactionGetParameterResult,
    ReactionStatusResult,    # components/system_information
    SystemInformationRobotPositionResult,
    SystemInformationEngineStatusResult,
]

# str, Enum classes → TypeAdapter(cls).json_schema()
ENUMS: list[type] = [
    ReturnCode,
    ComponentStatus,
    StreamStatus,
    CompletedStatus,
    ErrorType,
    ComponentFunction,
]

# ---------------------------------------------------------------------------
# Module mapping (for manifest.json generation)
# ---------------------------------------------------------------------------

MODULE_MAP: dict[type, str] = {
    # hri
    Result: "hri",
    Parameter: "hri",
    Argument: "hri",
    CommandUnit: "hri",
    ConcurrentCommands: "hri",
    CommandUnitSequence: "hri",
    ReturnCode: "hri",
    # common
    ComponentStatus: "common",
    StreamStatus: "common",
    # service
    CompletedStatus: "service",
    ErrorType: "service",
    NotifyErrorParams: "service",
    CompletedParams: "service",
    NotifyEventParams: "service",
    ProfileChangedParams: "service",
    # profiles
    ComponentFunction: "profiles",
    RoISIdentifierType: "profiles",
    ParameterProfile: "profiles",
    MessageProfile: "profiles",
    CommandMessageProfile: "profiles",
    QueryMessageProfile: "profiles",
    EventMessageProfile: "profiles",
    HRIComponentProfile: "profiles",
    HRIEngineProfileType: "profiles",
    # contract
    DiscoverRequest: "contract",
    DiscoverResponse: "contract",
    CommandRequest: "contract",
    InvokeResponse: "contract",
    QueryRequest: "contract",
    QueryResponse: "contract",
    SubscribeRequest: "contract",
    SubscribeResponse: "contract",
    EventEnvelope: "contract",
    # catalog
    **{cls: "catalog" for cls in CATALOG_MODELS},
    # components/person_detection
    PersonDetectedEvent: "components/person-detection",
    PersonDetectionStatusResult: "components/person-detection",
    # components/navigation
    NavigationSetParameter: "components/navigation",
    NavigationSetParameterResult: "components/navigation",
    NavigationGetParameterResult: "components/navigation",
    NavigationStatusResult: "components/navigation",
    NavigationReachedTargetEvent: "components/navigation",
    # components/reaction
    ReactionSetParameter: "components/reaction",
    ReactionSetParameterResult: "components/reaction",
    ReactionGetParameterResult: "components/reaction",
    ReactionStatusResult: "components/reaction",
    # components/system-information
    SystemInformationRobotPositionResult: "components/system-information",
    SystemInformationEngineStatusResult: "components/system-information",
}

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

# scripts/export_schema.py → scripts/ → python/ → interfaces/ → schema/
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def package_version() -> str:
    """The interfaces package version, written as the npm and NuGet packages spell it.

    The manifest belongs to the interfaces package, so it carries that package's version
    instead of a hard-coded string. PEP 440 "0.1.0a2" becomes "0.1.0-alpha.2".
    """
    version = str(tomllib.loads(PYPROJECT.read_text())["project"]["version"])
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:a(\d+))?", version)
    if match is None:
        raise ValueError(f"Unsupported version in {PYPROJECT}: {version}")
    base, alpha = match.groups()
    return f"{base}-alpha.{alpha}" if alpha else base


def export_model(model: type[BaseModel]) -> dict[str, object]:
    """Generate JSON Schema for a BaseModel subclass."""
    return model.model_json_schema()


def export_enum(enum_cls: type) -> dict[str, object]:
    """Generate JSON Schema for a str-Enum class."""
    return TypeAdapter(enum_cls).json_schema()


def write_schema(name: str, schema: dict[str, object]) -> Path:
    """Write a schema dict to <SCHEMA_DIR>/<name>.schema.json (no trailing newline).

    Injects a ``$comment`` field marking the file as auto-generated. This is a
    non-normative annotation: JSON Schema consumers ignore it, but it signals to
    human readers that the file must not be hand-edited.
    """
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    path = SCHEMA_DIR / f"{name}.schema.json"
    # Insert $comment at the top so it is the first key in the output.
    schema_with_comment: dict[str, object] = {
        "$comment": "GENERATED FROM interfaces/python: DO NOT EDIT. Run scripts/export_schema.py.",
        **schema,
    }
    text = json.dumps(schema_with_comment, indent=2, ensure_ascii=False)
    path.write_text(text)
    return path


def write_manifest() -> Path:
    """Generate manifest.json mapping module names to schema file lists."""
    modules: dict[str, list[str]] = {}
    for cls in [*MODELS, *ENUMS]:
        module = MODULE_MAP[cls]
        modules.setdefault(module, []).append(f"{cls.__name__}.schema.json")
    # Sort file lists for deterministic output
    for file_list in modules.values():
        file_list.sort()
    manifest = {"version": package_version(), "modules": modules}
    path = SCHEMA_DIR / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return path


def write_catalog() -> Path:
    """Write catalog.json, the method table the TypeScript and C# generators read."""
    path = SCHEMA_DIR / "catalog.json"
    path.write_text(json.dumps(catalog_document(), indent=2, ensure_ascii=False))
    return path


def write_profiles() -> Path:
    """Write profiles.json, the profile constants the TypeScript generator reads."""
    path = SCHEMA_DIR / "profiles.json"
    path.write_text(json.dumps(profiles_document(), indent=2, ensure_ascii=False))
    return path


def main() -> None:
    """Export all models and enums to interfaces/schema/."""
    written: list[str] = []

    for model in MODELS:
        schema = export_model(model)
        path = write_schema(model.__name__, schema)
        written.append(path.name)

    for enum_cls in ENUMS:
        schema = export_enum(enum_cls)
        path = write_schema(enum_cls.__name__, schema)
        written.append(path.name)

    manifest_path = write_manifest()
    written.append(manifest_path.name)

    catalog_path = write_catalog()
    written.append(catalog_path.name)

    profiles_path = write_profiles()
    written.append(profiles_path.name)

    print(f"Exported {len(written)} files to {SCHEMA_DIR}:")
    for name in sorted(written):
        print(f"  {name}")


if __name__ == "__main__":
    main()